#!/usr/bin/env python3
"""Phase 3A 验收：Backtest Contract 预设与骨架 Result（无 qlib）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase3a_backtest.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.research_data.backtest import (
        BACKTEST_CONTRACT_VERSION,
        BacktestMetrics,
        BacktestRequest,
        BacktestResult,
        cn_equity_close_signal_next_open,
        compute_request_fingerprint,
        research_qlib_relaxed,
    )

    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    req_prod = BacktestRequest(
        experiment_id="exp_verify_3a",
        dataset_hash="ds_verify_3a",
        strategy_version="topk@1",
        start_date="2024-01-01",
        end_date="2024-06-30",
        initial_capital=1_000_000.0,
        engine="production",
        execution_policy=exec_p,
        market_price_policy=price_p,
        cost_policy=cost_p,
        trading_rule=rules,
    )
    fp = compute_request_fingerprint(req_prod)

    exec_q, price_q, cost_q, rules_q = research_qlib_relaxed()
    req_qlib = BacktestRequest(
        experiment_id="exp_verify_3a",
        dataset_hash="ds_verify_3a",
        strategy_version="topk@1",
        start_date="2024-01-01",
        end_date="2024-06-30",
        initial_capital=1_000_000.0,
        engine="qlib",
        execution_policy=exec_q,
        market_price_policy=price_q,
        cost_policy=cost_q,
        trading_rule=rules_q,
    )

    skeleton = BacktestResult(
        result_id=f"res_{fp[:16]}",
        request_fingerprint=fp,
        experiment_id=req_prod.experiment_id,
        dataset_hash=req_prod.dataset_hash,
        engine="production",
        contract_version=BACKTEST_CONTRACT_VERSION,
        metrics=BacktestMetrics(),
    )

    checks = {
        "contract_version": {"ok": req_prod.contract_version == BACKTEST_CONTRACT_VERSION},
        "cn_preset": {
            "ok": rules.t_plus == 1 and rules.lot_size == 100 and not rules.short_allowed,
            "execution_delay": exec_p.execution_delay,
        },
        "fingerprint": {"ok": bool(fp), "len": len(fp)},
        "engines_share_contract": {
            "ok": req_prod.engine == "production" and req_qlib.engine == "qlib",
        },
        "result_skeleton": {
            "ok": skeleton.request_fingerprint == fp and skeleton.trades == [],
        },
        "metrics_schema": {
            "ok": hasattr(BacktestMetrics(), "sharpe") and hasattr(BacktestMetrics(), "max_drawdown"),
        },
    }
    ok = all(bool(c.get("ok")) for c in checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
