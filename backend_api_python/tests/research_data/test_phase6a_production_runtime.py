"""Phase 6A：Production Runtime / Online Data 验收。"""

from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services.production_runtime import (
    ProductionRuntimeError,
    ProductionRuntimeService,
    RuntimeStateError,
)
from app.services.production_runtime.hash import compute_idempotency_key
from app.services.production_runtime.session import MarketSchedule
from app.services.production_runtime.state_machine import assert_transition, can_transition

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_runtime_golden.golden import (  # noqa: E402
    deployed_bundle,
    intraday_now,
    make_env,
    tick_meta,
    trading_days,
)


def test_state_machine_rules():
    assert can_transition("STARTING", "READY")
    assert_transition("READY", "RUNNING")
    with pytest.raises(RuntimeStateError):
        assert_transition("STOPPED", "RUNNING")


def test_session_phases_cn_a():
    sched = MarketSchedule()
    sh = ZoneInfo("Asia/Shanghai")
    day = datetime(2020, 1, 2, tzinfo=sh)

    def at(h, m):
        return day.replace(hour=h, minute=m).astimezone(timezone.utc)

    assert sched.phase_at("CN_A", at(8, 0)) == "PRE_MARKET"
    assert sched.phase_at("CN_A", at(9, 32)) == "MARKET_OPEN"
    assert sched.phase_at("CN_A", at(10, 30)) == "INTRADAY"
    assert sched.phase_at("CN_A", at(14, 55)) == "PRE_CLOSE"
    assert sched.phase_at("CN_A", at(15, 2)) == "MARKET_CLOSE"
    assert sched.phase_at("CN_A", at(16, 0)) == "POST_MARKET"


def test_start_requires_deployed_and_paper_only(tmp_path):
    _, registry, bridge, rt = make_env(tmp_path)
    with pytest.raises(ProductionRuntimeError):
        rt.start("missing_bundle", environment="PAPER")
    # freeze but not deploy
    from production_bridge_golden.golden import SHASH, freeze_meta

    meta = freeze_meta()
    r = bridge.freeze(SHASH, metadata=meta)
    with pytest.raises(ProductionRuntimeError):
        rt.start(r.bundle_hash, environment="PAPER")
    # LIVE 禁止
    dep = deployed_bundle(bridge)
    with pytest.raises(ProductionRuntimeError):
        rt.start(dep.bundle_hash, environment="LIVE")  # type: ignore[arg-type]


def test_paper_tick_produces_intents(tmp_path):
    _, registry, bridge, rt = make_env(tmp_path)
    dep = deployed_bundle(bridge)
    inst = rt.start(dep.bundle_hash, market="CN_A", environment="PAPER")
    assert inst.status == "READY"
    day = trading_days(1)[0]
    result = rt.tick(
        inst.runtime_id,
        now=intraday_now(day),
        metadata=tick_meta(day),
    )
    assert result.status == "OK"
    assert len(result.order_intents) >= 1
    assert result.run_id
    assert "ORDER_INTENT_CREATED" in result.events
    assert "FEATURE_COMPUTED" in result.events
    # 产物
    assert Path(inst.storage_uri, "manifest.json").is_file() or Path(
        registry.get_production_runtime(inst.runtime_id).storage_uri
    ).joinpath("manifest.json").is_file()
    events = registry.list_runtime_events(inst.runtime_id)
    assert any(e.event_type == "BUNDLE_LOADED" for e in events)
    assert any(e.event_type == "ORDER_INTENT_CREATED" for e in events)


def test_idempotent_tick(tmp_path):
    _, registry, bridge, rt = make_env(tmp_path)
    dep = deployed_bundle(bridge)
    inst = rt.start(dep.bundle_hash, environment="PAPER")
    day = trading_days(1)[0]
    meta = tick_meta(day)
    r1 = rt.tick(inst.runtime_id, now=intraday_now(day), metadata=meta)
    r2 = rt.tick(inst.runtime_id, now=intraday_now(day), metadata=meta)
    assert r1.status == "OK"
    assert r2.status == "SKIPPED_IDEMPOTENT"
    assert r2.reused is True
    assert r2.run_id == r1.run_id
    # force_new_run 破幂等
    meta2 = tick_meta(day, force_new_run=True)
    meta2["decision_bucket"] = "INTRADAY_TEST_2"
    r3 = rt.tick(inst.runtime_id, now=intraday_now(day), metadata=meta2)
    assert r3.status == "OK"
    assert r3.run_id != r1.run_id


def test_data_stale_event(tmp_path):
    _, registry, bridge, rt = make_env(tmp_path)
    dep = deployed_bundle(bridge)
    inst = rt.start(dep.bundle_hash, environment="SHADOW")
    day = trading_days(1)[0]
    result = rt.tick(
        inst.runtime_id,
        now=intraday_now(day),
        metadata={
            "trading_date": day.isoformat(),
            "session_phase": "INTRADAY",
            "decision_bucket": "STALE_TEST",
            "force_intraday": True,
            "instruments": ["CNStock:999999"],
            "universe_membership": ["CNStock:999999"],
            # 无 price_bars / factor_rows → DATA_STALE
        },
    )
    assert result.status == "FAILED"
    assert "DATA_STALE" in result.events
    assert (result.metadata or {}).get("error") == "DATA_STALE"


def test_pause_resume_stop(tmp_path):
    _, _, bridge, rt = make_env(tmp_path)
    dep = deployed_bundle(bridge)
    inst = rt.start(dep.bundle_hash, environment="PAPER")
    day = trading_days(1)[0]
    rt.tick(inst.runtime_id, now=intraday_now(day), metadata=tick_meta(day))
    paused = rt.pause(inst.runtime_id)
    assert paused.status == "PAUSED"
    # PAUSED 不可 tick
    bad = rt.tick(
        inst.runtime_id,
        now=intraday_now(day),
        metadata=tick_meta(day, force_new_run=True),
    )
    assert bad.status == "FAILED"
    resumed = rt.resume(inst.runtime_id)
    assert resumed.status in ("RUNNING", "READY")
    stopped = rt.stop(inst.runtime_id)
    assert stopped.status == "STOPPED"


def test_idempotency_key_stable():
    k1 = compute_idempotency_key(
        bundle_hash="b1",
        trading_date="2020-01-02",
        session_phase="INTRADAY",
        decision_bucket="INTRADAY_TEST",
        instruments=["A", "B"],
    )
    k2 = compute_idempotency_key(
        bundle_hash="b1",
        trading_date="2020-01-02",
        session_phase="INTRADAY",
        decision_bucket="INTRADAY_TEST",
        instruments=["B", "A"],
    )
    assert k1 == k2


def test_domain_ast_isolation():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "production_runtime"
    )
    forbidden_substrings = (
        "qlib",
        "broker",
        "PendingOrderWorker",
        "pending_orders",
        "DataSourceFactory",
        "backtest_production",
        "quick_trade",
    )
    for py in root.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    assert name != "qlib" and not name.startswith("qlib.")
                    for bad in forbidden_substrings:
                        if bad == "qlib":
                            continue
                        assert bad not in name
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("qlib")
                for bad in (
                    "broker",
                    "PendingOrderWorker",
                    "pending_orders",
                    "DataSourceFactory",
                    "backtest_production",
                    "quick_trade",
                ):
                    assert bad not in mod
                for alias in node.names or []:
                    assert alias.name not in (
                        "PendingOrderWorker",
                        "DataSourceFactory",
                        "ProductionBacktestEngine",
                    )
