#!/usr/bin/env python3
"""Phase 3C 验收：Execution Rules / Cost / OrderIntent 链路（无 qlib）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase3c_execution_rules.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.research_data.backtest.execution import (
        REASON_EXECUTION_DELAY,
        REASON_LIMIT_DOWN,
        REASON_LIMIT_UP,
        REASON_LOT_SIZE_FLOOR,
        REASON_SUSPENDED,
        MarketBar,
        adjust_lot_quantity,
        compute_cost_breakdown,
        decide_execution,
        resolve_execution_date,
        run_pipeline,
    )
    from app.services.research_data.backtest.ledger import PortfolioSnapshot
    from app.services.research_data.backtest.presets import cn_equity_close_signal_next_open
    from app.services.research_data.contracts import TargetPosition

    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    cal = [date(2024, 5, 6), date(2024, 5, 7), date(2024, 5, 8)]

    # 1) T+1
    exec_day = resolve_execution_date(
        "2024-05-06", "T+1", market_calendar_id=rules.market_calendar_id, calendar=cal
    )
    t_plus_ok = exec_day == date(2024, 5, 7)

    targets = [
        TargetPosition(
            instrument_key="CNStock:600519",
            trading_date="2024-05-06",
            portfolio_id="p1",
            strategy_version="verify@1",
            dataset_hash="ds",
            timestamp=datetime(2024, 5, 6, 15, 0, 0),
            target_quantity=100.0,
            target_weight=0.0,
            signal_id="sig",
        )
    ]
    portfolio = PortfolioSnapshot(
        trading_date="2024-05-06", cash=1_000_000.0, total_value=1_000_000.0
    )
    pipe_t = run_pipeline(
        targets=targets,
        portfolio=portfolio,
        bars={"CNStock:600519": MarketBar(
            instrument_key="CNStock:600519",
            trading_date="2024-05-06",
            open=100.0,
            close=100.0,
        )},
        execution_policy=exec_p,
        trading_rule=rules,
        cost_policy=cost_p,
        market_price_policy=price_p,
        execution_date="2024-05-06",
        calendar=cal,
    )
    delay_ok = all(d.reason == REASON_EXECUTION_DELAY for d in pipe_t.decisions)

    pipe_t1 = run_pipeline(
        targets=targets,
        portfolio=portfolio,
        bars={"CNStock:600519": MarketBar(
            instrument_key="CNStock:600519",
            trading_date="2024-05-07",
            open=100.0,
            close=101.0,
        )},
        execution_policy=exec_p,
        trading_rule=rules,
        cost_policy=cost_p,
        market_price_policy=price_p,
        execution_date="2024-05-07",
        calendar=cal,
    )
    fill_ok = any(t.status in ("FILLED", "PARTIAL") and t.quantity == 100 for t in pipe_t1.trades)

    # 2) Lot
    lot = adjust_lot_quantity(155, rules)
    lot_ok = (
        lot.executable_quantity == 100
        and lot.rejected_quantity == 55
        and lot.reason == REASON_LOT_SIZE_FLOOR
    )

    # 3) Limit up / down
    bar_up = MarketBar(
        instrument_key="CNStock:600519",
        trading_date="2024-05-07",
        open=110.0,
        close=110.0,
        is_limit_up=True,
    )
    d_up = decide_execution(
        instrument_key=bar_up.instrument_key,
        side="BUY",
        quantity=100,
        bar=bar_up,
        rule=rules,
        fill_price=110.0,
    )
    bar_dn = MarketBar(
        instrument_key="CNStock:600519",
        trading_date="2024-05-07",
        open=90.0,
        close=90.0,
        is_limit_down=True,
    )
    d_dn = decide_execution(
        instrument_key=bar_dn.instrument_key,
        side="SELL",
        quantity=100,
        bar=bar_dn,
        rule=rules,
        sellable_quantity=100,
        fill_price=90.0,
    )

    # 4) Suspension
    bar_sus = MarketBar(
        instrument_key="CNStock:600519",
        trading_date="2024-05-07",
        open=100.0,
        close=100.0,
        is_suspended=True,
    )
    d_sus = decide_execution(
        instrument_key=bar_sus.instrument_key,
        side="BUY",
        quantity=100,
        bar=bar_sus,
        rule=rules,
        fill_price=100.0,
    )

    # 5) Cost
    buy = compute_cost_breakdown(
        side="BUY", quantity=100, executed_price=10.0, cost_policy=cost_p
    )
    sell = compute_cost_breakdown(
        side="SELL", quantity=100, executed_price=10.0, cost_policy=cost_p
    )
    cost_ok = (
        abs(buy.net_cash_delta + buy.gross_value + buy.total_cost) < 1e-9
        and abs(sell.net_cash_delta - (sell.gross_value - sell.total_cost)) < 1e-9
    )

    # 6) Pipeline completeness
    pipe_ok = bool(
        pipe_t1.intents
        and pipe_t1.decisions
        and any(t.status in ("FILLED", "PARTIAL") for t in pipe_t1.trades)
        and pipe_t1.portfolio.positions
    )

    checks = {
        "t_plus_calendar": {"ok": t_plus_ok, "exec_day": str(exec_day)},
        "t_plus_gate": {"ok": delay_ok and fill_ok},
        "lot_floor": {
            "ok": lot_ok,
            "executable": lot.executable_quantity,
            "rejected": lot.rejected_quantity,
        },
        "limit_up": {"ok": (not d_up.executable) and d_up.reason == REASON_LIMIT_UP},
        "limit_down": {"ok": (not d_dn.executable) and d_dn.reason == REASON_LIMIT_DOWN},
        "suspension": {"ok": (not d_sus.executable) and d_sus.reason == REASON_SUSPENDED},
        "cost_identity": {"ok": cost_ok},
        "pipeline": {
            "ok": pipe_ok,
            "intent_qty": pipe_t1.intents[0].quantity if pipe_t1.intents else None,
            "position_qty": (
                pipe_t1.portfolio.positions[0].quantity if pipe_t1.portfolio.positions else None
            ),
        },
        "lot_rounding_contract": {"ok": rules.lot_rounding == "floor"},
    }
    ok = all(v.get("ok") for v in checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
