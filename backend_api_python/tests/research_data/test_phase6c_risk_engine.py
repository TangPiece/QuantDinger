"""Phase 6C：Risk Engine 验收。"""

from __future__ import annotations

import ast
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.portfolio_service.protocol import Account, CashBalance, Position
from app.services.risk_engine import RiskPolicy
from app.services.risk_engine.aggregate import apply_modifications
from app.services.risk_engine.policy import finalize_policy
from app.services.risk_engine.protocol import RiskResult

sys.path.insert(0, str(Path(__file__).resolve().parent))
from risk_engine_golden.golden import (  # noqa: E402
    DAY,
    INST_A,
    INST_B,
    default_policy,
    make_env,
    prices,
    sample_deltas,
    targets,
)


def test_policy_hash_stable():
    p1 = finalize_policy(RiskPolicy(policy_code="a", policy_version="1"))
    p2 = finalize_policy(RiskPolicy(policy_code="a", policy_version="1"))
    assert p1.policy_hash == p2.policy_hash
    p3 = finalize_policy(
        RiskPolicy(policy_code="a", policy_version="1", max_single_position_weight=0.2)
    )
    assert p3.policy_hash != p1.policy_hash


def test_clip_only_never_increases():
    deltas = sample_deltas(tw_a=0.15)
    results = [
        RiskResult(
            rule_code="MAX_SINGLE_POSITION",
            decision="MODIFY",
            instrument_key=INST_A,
            adjusted_target_weight=0.10,
            original_value=0.15,
            limit_value=0.10,
        )
    ]
    out = apply_modifications(deltas, results, equity=1_000_000, prices=prices())
    assert abs(out[0].target_weight) <= abs(deltas[0].target_weight) + 1e-12
    assert out[0].target_weight == pytest.approx(0.10)


def test_single_position_modify(tmp_path):
    _, _, _, risk = make_env(tmp_path)
    acct = Account(
        account_id="acc1",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    policy = default_policy(max_single_position_weight=0.10, clip_on_limit=True)
    r = risk.evaluate(
        deltas=sample_deltas(tw_a=0.15),
        account=acct,
        policy=policy,
        prices=prices(),
        metadata={
            "account_id": "acc1",
            "portfolio_id": "pf1",
            "trading_date": DAY.isoformat(),
            "apply_id": "ap1",
        },
    )
    assert r.verdict == "MODIFY"
    assert len(r.order_intents) >= 1
    assert r.adjusted_deltas[0].target_weight == pytest.approx(0.10)
    assert "RISK_MODIFY" in (r.order_intents[0].reason or "")


def test_single_position_reject(tmp_path):
    _, _, _, risk = make_env(tmp_path)
    acct = Account(
        account_id="acc1",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    policy = default_policy(max_single_position_weight=0.10, clip_on_limit=False)
    r = risk.evaluate(
        deltas=sample_deltas(tw_a=0.15),
        account=acct,
        policy=policy,
        prices=prices(),
        metadata={
            "account_id": "acc1",
            "portfolio_id": "pf1",
            "trading_date": DAY.isoformat(),
            "apply_id": "ap_rej",
        },
    )
    assert r.verdict == "REJECT"
    assert r.order_intents == []


def test_trading_status_limit_up(tmp_path):
    _, _, _, risk = make_env(tmp_path)
    acct = Account(
        account_id="acc1",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    r = risk.evaluate(
        deltas=sample_deltas(tw_a=0.05),
        account=acct,
        policy=default_policy(),
        prices=prices(),
        trading_status={INST_A: {"is_limit_up": True}},
        metadata={
            "account_id": "acc1",
            "portfolio_id": "pf1",
            "trading_date": DAY.isoformat(),
            "apply_id": "ap_lu",
        },
    )
    assert r.verdict == "REJECT"


def test_data_freshness(tmp_path):
    _, _, _, risk = make_env(tmp_path)
    acct = Account(
        account_id="acc1",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    now = datetime(2020, 1, 3, tzinfo=timezone.utc)
    stale = now - timedelta(days=3)
    r = risk.evaluate(
        deltas=sample_deltas(tw_a=0.05),
        account=acct,
        policy=default_policy(data_freshness_seconds=86400),
        prices=prices(),
        knowledge_time=now,
        market_data_as_of=stale,
        metadata={
            "account_id": "acc1",
            "portfolio_id": "pf1",
            "trading_date": DAY.isoformat(),
            "apply_id": "ap_stale",
        },
    )
    assert r.verdict == "REJECT"
    assert any(v.rule_code == "DATA_FRESHNESS" for v in r.violations)


def test_universe_and_account_state(tmp_path):
    _, _, _, risk = make_env(tmp_path)
    acct = Account(
        account_id="acc1",
        status="PAUSED",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    r = risk.evaluate(
        deltas=sample_deltas(tw_a=0.05),
        account=acct,
        policy=default_policy(),
        prices=prices(),
        metadata={
            "account_id": "acc1",
            "portfolio_id": "pf1",
            "trading_date": DAY.isoformat(),
            "apply_id": "ap_paused",
        },
    )
    assert r.verdict == "REJECT"

    acct2 = Account(
        account_id="acc2",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    r2 = risk.evaluate(
        deltas=sample_deltas(tw_a=0.05),
        account=acct2,
        policy=default_policy(
            require_universe=True, universe_membership=[INST_B]
        ),
        prices=prices(),
        metadata={
            "account_id": "acc2",
            "portfolio_id": "pf2",
            "trading_date": DAY.isoformat(),
            "apply_id": "ap_uni",
        },
    )
    assert r2.verdict == "REJECT"
    assert any(v.rule_code == "UNIVERSE" for v in r2.violations)


def test_idempotent(tmp_path):
    _, _, _, risk = make_env(tmp_path)
    acct = Account(
        account_id="acc1",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    meta = {
        "account_id": "acc1",
        "portfolio_id": "pf1",
        "trading_date": DAY.isoformat(),
        "apply_id": "ap_idem",
    }
    r1 = risk.evaluate(
        deltas=sample_deltas(tw_a=0.05),
        account=acct,
        policy=default_policy(),
        prices=prices(),
        metadata=meta,
    )
    r2 = risk.evaluate(
        deltas=sample_deltas(tw_a=0.05),
        account=acct,
        policy=default_policy(),
        prices=prices(),
        metadata=meta,
    )
    assert r1.status == "OK"
    assert r2.status == "SKIPPED_IDEMPOTENT"
    assert r2.risk_run_id == r1.risk_run_id


def test_shadow_dry_to_risk(tmp_path):
    _, _, portfolio, risk = make_env(tmp_path)
    acct = portfolio.open_account(environment="SHADOW", initial_cash=1_000_000)
    apply = portfolio.apply_targets(
        acct.account_id,
        targets(w_a=0.08, w_b=0.05),
        trading_date=DAY.isoformat(),
        prices=prices(),
        apply_mode="SHADOW_DRY",
        runtime_id="rt1",
        run_id="run1",
    )
    assert apply.apply_mode == "SHADOW_DRY"
    r = risk.evaluate(
        apply,
        policy=default_policy(max_single_position_weight=0.20),
        prices=prices(),
        metadata={"universe_membership": [INST_A, INST_B]},
    )
    assert r.verdict in ("ALLOW", "MODIFY", "ALLOW_REDUCE")
    assert len(r.order_intents) >= 1
    assert r.snapshot is not None
    assert r.events


def test_domain_ast_isolation():
    root = (
        Path(__file__).resolve().parents[2] / "app" / "services" / "risk_engine"
    )
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    assert name != "qlib" and not name.startswith("qlib.")
                    assert "broker" not in name.lower()
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("qlib")
                assert "pending_order" not in mod.lower()
                assert "broker" not in mod.lower()
                assert "strategy_v2" not in mod
                assert "live_trading" not in mod
                for alias in node.names or []:
                    assert alias.name not in (
                        "PendingOrderWorker",
                        "DataSourceFactory",
                    )
