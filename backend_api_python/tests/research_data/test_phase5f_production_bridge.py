"""Phase 5F：Production Bridge 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.research_data.production_bridge import (
    ProductionBridgeError,
    StateTransitionError,
    compute_production_bundle_hash,
)
from app.services.research_data.production_bridge.feature_parity import (
    run_feature_parity,
)
from app.services.research_data.production_bridge.freeze import build_bundle_spec
from app.services.research_data.production_bridge.state_machine import (
    assert_transition,
    is_immutable,
)
from app.services.research_data.contracts import CrossValidationSummary

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_bridge_golden.golden import (  # noqa: E402
    CVHASH,
    SCODE,
    SHASH,
    freeze_meta,
    make_env,
    promote_to_deployed,
    run_infer,
    trading_days,
)


def test_state_machine_rules():
    assert_transition("DRAFT", "VALIDATED")
    with pytest.raises(StateTransitionError):
        assert_transition("DRAFT", "DEPLOYED")
    assert is_immutable("APPROVED")
    assert not is_immutable("DRAFT")


def test_feature_parity_pass_and_fail():
    rows = [
        {"instrument_key": "A", "trading_date": "2020-01-02", "score": 1.0},
        {"instrument_key": "B", "trading_date": "2020-01-02", "score": 2.0},
    ]
    assert run_feature_parity(rows, rows).passed
    bad = [
        {"instrument_key": "A", "trading_date": "2020-01-02", "score": 1.0},
        {"instrument_key": "B", "trading_date": "2020-01-02", "online_value": 9.0},
    ]
    # online_value 优先 → 与 offline score 不一致
    offline = [
        {"instrument_key": "A", "trading_date": "2020-01-02", "score": 1.0},
        {"instrument_key": "B", "trading_date": "2020-01-02", "score": 2.0},
    ]
    assert not run_feature_parity(offline, bad).passed


def test_freeze_validate_promote_approve_deploy(tmp_path):
    _, registry, svc = make_env(tmp_path)
    r = promote_to_deployed(svc)
    assert r.summary.status == "DEPLOYED"
    assert r.deployment is not None
    assert registry.get_production_bundle(r.bundle_hash).status == "DEPLOYED"
    art = Path(r.summary.storage_uri)
    assert (art / "manifest.json").is_file()
    assert (art / "checksums.json").is_file()
    assert (art / "strategy" / "snapshot.json").is_file()


def test_approved_immutable(tmp_path):
    _, _, svc = make_env(tmp_path)
    meta = freeze_meta()
    r = svc.freeze(SHASH, metadata=meta)
    r = svc.validate(r.bundle_hash, metadata=meta)
    r = svc.promote(r.bundle_hash)
    r = svc.approve(r.bundle_hash)
    with pytest.raises(StateTransitionError):
        svc.validate(r.bundle_hash, metadata=meta)


def test_promote_requires_cv_pass(tmp_path):
    _, registry, svc = make_env(tmp_path)
    # 覆盖 CV 为 FAILED
    registry.upsert_research_cross_validation(
        CrossValidationSummary(
            cv_hash=CVHASH,
            strategy_hash=SHASH,
            status="FAILED",
        )
    )
    meta = freeze_meta()
    r = svc.freeze(SHASH, metadata=meta)
    r = svc.validate(r.bundle_hash, metadata=meta)
    with pytest.raises(ProductionBridgeError):
        svc.promote(r.bundle_hash)


def test_infer_order_intents(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = promote_to_deployed(svc)
    day = trading_days(1)[0]
    resp = run_infer(svc, r.bundle_hash, day)
    assert resp.status == "OK"
    assert len(resp.signals) >= 1
    assert len(resp.targets) >= 1
    assert len(resp.order_intents) >= 1
    assert all(i.reason == "DRY_RUN_PRODUCTION_BRIDGE" for i in resp.order_intents)


def test_data_quality_stop(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = promote_to_deployed(svc)
    day = trading_days(1)[0]
    from app.services.research_data.production_bridge import InferenceRequest

    resp = svc.infer(
        InferenceRequest(bundle_hash=r.bundle_hash, trading_date=day),
        metadata={
            "factor_rows": [
                {
                    "instrument_key": "CNStock:600000",
                    "trading_date": day.isoformat(),
                    "score": float("nan"),
                }
            ],
            "price_bars": [
                {
                    "instrument_key": "CNStock:600000",
                    "trading_date": day.isoformat(),
                    "open": 10.0,
                    "close": 10.0,
                }
            ],
            "universe_membership": ["CNStock:600000"],
        },
    )
    assert resp.status == "STOPPED"


def test_rollback(tmp_path):
    _, registry, svc = make_env(tmp_path)
    # v1
    r1 = promote_to_deployed(svc)
    h1 = r1.bundle_hash
    # v2：改 parent + dataset 产生新 hash
    meta = freeze_meta()
    meta["dataset_hash"] = "dh_5f_v2"
    meta["parent_bundle_hash"] = h1
    r2 = svc.freeze(SHASH, metadata=meta)
    r2 = svc.validate(r2.bundle_hash, metadata=meta)
    r2 = svc.promote(r2.bundle_hash)
    r2 = svc.approve(r2.bundle_hash)
    r2 = svc.deploy(r2.bundle_hash)
    assert r2.bundle_hash != h1
    assert registry.get_active_deployment(SCODE).bundle_hash == r2.bundle_hash
    # rollback to v1
    rb = svc.rollback(SCODE, h1)
    assert rb.summary.bundle_hash == h1
    assert rb.summary.status == "DEPLOYED"
    assert registry.get_active_deployment(SCODE).bundle_hash == h1


def test_hash_stable():
    cv = CrossValidationSummary(
        cv_hash=CVHASH, strategy_hash=SHASH, status="PASSED"
    )
    s1 = build_bundle_spec(
        None,
        cv,
        metadata={
            "strategy_code": SCODE,
            "allow_missing_strategy": True,
            "signal_definition_json": {},
        },
    )
    assert compute_production_bundle_hash(s1) == compute_production_bundle_hash(s1)


def test_domain_ast_isolation():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "production_bridge"
    )
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    assert name != "qlib" and not name.startswith("qlib.")
                    assert "backtest_production" not in name
                    assert "broker" not in name.lower()
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("qlib")
                assert "backtest_production" not in mod
                for alias in node.names or []:
                    assert alias.name != "ProductionBacktestEngine"
