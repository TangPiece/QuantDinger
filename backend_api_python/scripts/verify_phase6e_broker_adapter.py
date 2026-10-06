#!/usr/bin/env python3
"""Phase 6E 验收：Broker Adapter。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6e_broker_adapter.py
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
    pkg = ROOT / "app" / "services" / "broker_adapter"
    forbidden = ("qlib", "strategy_v2", "live_trading", "pending_order", "DataSourceFactory")
    for py in pkg.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    for frag in forbidden:
                        if frag in name:
                            return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for frag in forbidden:
                    if frag in mod:
                        return False
    return True


def main() -> int:
    from broker_adapter_golden.golden import (
        INST_A,
        make_env,
        prices,
        sample_intent,
    )
    from app.services.broker_adapter import BrokerAdapterService
    from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError
    from app.services.broker_adapter.adapters.alpaca import AlpacaPaperAdapter
    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.registry import LocalJsonRegistry

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6e_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    # Paper fill
    _, registry, portfolio, _, oms, broker_svc, _ = make_env(tmp)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=5, reason="v_fill")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
    )
    checks["paper_fill"] = r.orders[0].status == "FILLED" and bool(r.fills)

    # SANDBOX async + drain + partial
    _, _, portfolio2, _, oms2, _, adapter2 = make_env(tmp / "sb", mode="SANDBOX")
    acct2 = portfolio2.open_account(initial_cash=1_000_000)
    pid2 = acct2.metadata["default_portfolio_id"]
    rp = oms2.submit_intents(
        [sample_intent(qty=10, reason="v_partial")],
        account_id=acct2.account_id,
        portfolio_id=pid2,
        environment="SANDBOX",
        prices=prices(),
        metadata={"simulated": {"partial_fills": [3.0, 7.0]}},
    )
    checks["broker_submit_pending"] = rp.orders[0].status == "SUBMITTED"
    n = oms2.drain_outbox()
    checks["drain_broker_submit"] = n >= 1
    o = oms2.get_order(rp.orders[0].order_id)
    checks["partial_fill"] = o.status == "FILLED" and len(oms2.list_fills(o.order_id)) == 2

    # UNKNOWN recover
    ru = oms2.submit_intents(
        [sample_intent(qty=2, reason="v_unk")],
        account_id=acct2.account_id,
        portfolio_id=pid2,
        environment="SANDBOX",
        prices=prices(),
        metadata={"simulated": {"timeout_unknown": True}},
    )
    oms2.drain_outbox()
    checks["unknown"] = oms2.get_order(ru.orders[0].order_id).status == "UNKNOWN"
    recovered = oms2.recover_unknown_order(ru.orders[0].order_id)
    checks["unknown_recover"] = recovered.status in (
        "ACKNOWLEDGED",
        "FILLED",
        "PARTIALLY_FILLED",
    )

    # dedup + ws（独立 adapter，避免会话历史污染）
    from app.services.oms.protocol import Order
    from app.services.broker_adapter import SimulatedBrokerAdapter

    sim = SimulatedBrokerAdapter(execution_mode="SANDBOX", prices=prices())
    sim.connect()
    order = Order(
        order_id="v_oid",
        client_order_id="v_clid",
        instrument_key=INST_A,
        quantity=1,
        idempotency_key="v_idem",
        metadata={"simulated": {"duplicate_execution": True}},
    )
    sim.submit_order(order)
    seen: list = []
    n1 = sim.pump_events(lambda er: seen.append(er))
    checks["dedup"] = n1 == 1 and len(seen) == 1
    sim.ws.disconnect()
    sim.reconnect_ws()
    n2 = sim.pump_events(lambda er: seen.append(er))
    checks["ws_reconnect_dedup"] = n2 == 0

    # raw / link
    report = broker_svc.submit_order(
        Order(
            order_id="link1",
            client_order_id="link_clid",
            instrument_key=INST_A,
            quantity=1,
            idempotency_key="link_idem",
        )
    )
    try:
        link = registry.get_order_link_by_client_id("link_clid")
        checks["order_link"] = link.order_id == "link1"
    except KeyError:
        checks["order_link"] = False

    # LIVE forbidden
    try:
        BrokerAdapterService(
            LocalCanonicalStore(root=tmp / "c2"),
            LocalJsonRegistry(root=tmp / "r2"),
            execution_mode="LIVE",  # type: ignore[arg-type]
        )
        checks["live_forbidden"] = False
    except BrokerAdapterError as exc:
        checks["live_forbidden"] = exc.code == AdapterErrorCode.LIVE_FORBIDDEN

    # Alpaca reference present
    checks["alpaca_reference"] = AlpacaPaperAdapter.execution_mode == "ALPACA_PAPER"
    checks["alpaca_paper_optional"] = True  # 无密钥时跳过实连

    print(json.dumps({"tmp": str(tmp), "checks": checks}, indent=2, ensure_ascii=False))
    ok = all(checks.values())
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
