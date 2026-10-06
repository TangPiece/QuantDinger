#!/usr/bin/env python3
"""Phase 6D 验收：OMS / Order Lifecycle。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6d_oms.py
"""

from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def _domain_isolation() -> bool:
    pkg = ROOT / "app" / "services" / "oms"
    for py in pkg.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    if name == "qlib" or name.startswith("qlib."):
                        return False
                    if "pending_order" in name.lower() or "live_trading" in name:
                        return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("qlib") or "strategy_v2" in mod:
                    return False
                if "live_trading" in mod or "pending_order" in mod:
                    return False
                if "DataSourceFactory" in mod:
                    return False
                # 允许本包 paper_broker；禁止其它 broker adapter
                if "broker" in mod.lower() and "paper_broker" not in mod:
                    return False
    return True


def main() -> int:
    from oms_golden.golden import (
        DAY,
        INST_A,
        default_policy,
        make_env,
        prices,
        sample_intent,
    )
    from app.services.portfolio_service.protocol import (
        Account,
        CashBalance,
        PositionDelta,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6d_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, portfolio, risk, oms = make_env(tmp)
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]

    r = oms.submit_intents(
        [sample_intent(qty=100, reason="v_fill")],
        account_id=acct.account_id,
        portfolio_id=pid,
        risk_run_id="v_rr",
        policy_hash="v_ph",
        prices=prices(),
    )
    checks["intent_to_filled"] = (
        len(r.orders) == 1 and r.orders[0].status == "FILLED" and bool(r.fills)
    )
    checks["client_order_id"] = bool(r.orders[0].client_order_id)
    checks["idempotency_key"] = bool(r.orders[0].idempotency_key)

    r2 = oms.submit_intents(
        [sample_intent(qty=100, reason="v_fill")],
        account_id=acct.account_id,
        portfolio_id=pid,
        risk_run_id="v_rr",
        prices=prices(),
    )
    checks["idempotent"] = r2.orders[0].order_id == r.orders[0].order_id

    pos = {p.instrument_key: p for p in portfolio.get_positions(pid)}
    checks["fill_to_position"] = INST_A in pos and abs(pos[INST_A].quantity - 100) < 1e-6

    # partial
    rp = oms.submit_intents(
        [sample_intent(qty=50, reason="v_partial")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
        metadata={"paper_broker": {"partial_fills": [20.0, 30.0]}},
    )
    checks["partial_fill"] = (
        rp.orders[0].status == "FILLED" and len(rp.fills) == 2
    )

    # cancel resting
    rc = oms.submit_intents(
        [sample_intent(qty=10, algo="LIMIT", limit_price=1.0, reason="v_cxl")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices={INST_A: 10.0},
    )
    cancelled = oms.cancel(rc.orders[0].order_id)
    checks["cancel"] = cancelled.status == "CANCELLED"

    # replace
    rr = oms.submit_intents(
        [sample_intent(qty=10, algo="LIMIT", limit_price=1.0, reason="v_rpl")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices={INST_A: 10.0},
    )
    replaced = oms.replace(rr.orders[0].order_id, quantity=8.0)
    checks["replace"] = replaced.version == 2 and replaced.quantity == 8.0

    # unknown
    ru = oms.submit_intents(
        [sample_intent(qty=5, reason="v_unk")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
        metadata={"paper_broker": {"timeout_unknown": True}},
    )
    checks["unknown"] = ru.orders[0].status == "UNKNOWN"

    checks["outbox"] = bool(r.outbox_ids)

    # 6C → 6D
    risk_acct = Account(
        account_id="v_risk",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    px = prices()
    tw = 0.02
    tq = (tw * 1_000_000) / px[INST_A]
    ev = risk.evaluate(
        deltas=[
            PositionDelta(
                instrument_key=INST_A,
                current_weight=0.0,
                target_weight=tw,
                delta_weight=tw,
                current_quantity=0.0,
                target_quantity=tq,
                delta_quantity=tq,
                side="BUY",
                notional=tq * px[INST_A],
            )
        ],
        account=risk_acct,
        policy=default_policy(),
        prices=px,
        metadata={
            "account_id": acct.account_id,
            "portfolio_id": pid,
            "trading_date": DAY.isoformat(),
            "apply_id": "v_ap",
        },
    )
    chain = oms.submit_intents(
        ev.order_intents,
        account_id=acct.account_id,
        portfolio_id=pid,
        risk_run_id=ev.risk_run_id,
        policy_hash=ev.policy_hash,
        prices=px,
    )
    checks["risk_to_oms"] = bool(chain.orders) and chain.orders[0].status in (
        "FILLED",
        "PARTIALLY_FILLED",
        "ACKNOWLEDGED",
        "REJECTED",
    )

    # registry roundtrip
    loaded = oms.get_order(r.orders[0].order_id)
    checks["registry_get"] = loaded.order_id == r.orders[0].order_id

    print(json.dumps({"tmp": str(tmp), "checks": checks}, indent=2, ensure_ascii=False))
    ok = all(checks.values())
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
