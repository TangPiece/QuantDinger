"""Qlib 子进程入口：qlib.init → backtest → 写结果后退出。

本文件是包内唯一允许 ``import qlib`` 的模块（进程隔离边界）。
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any


def run_worker(payload_path: str, result_path: str) -> int:
    """读取 payload JSON，执行回测，写入 result JSON。"""
    try:
        payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
        result = _execute(payload)
        Path(result_path).write_text(
            json.dumps(result, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        err = {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        Path(result_path).write_text(
            json.dumps(err, ensure_ascii=False), encoding="utf-8"
        )
        return 1


def _execute(payload: dict[str, Any]) -> dict[str, Any]:
    """优先真实 Qlib；失败或无 cache 时回落说明错误。"""
    cache_path = str(payload.get("cache_path") or "")
    strategy_cfg = payload.get("strategy_config") or {}
    exchange_kwargs = dict(payload.get("exchange_kwargs") or {})
    spec = payload.get("spec") or {}
    start = str(spec.get("start_date") or "")
    end = str(spec.get("end_date") or "")
    initial_nav = float(spec.get("initial_nav") or 1.0)

    weights_records = strategy_cfg.get("weights") or []
    if not weights_records:
        return {
            "ok": True,
            "mode": "empty_weights",
            "metrics": {"total_return": 0.0, "final_nav": initial_nav},
        }

    if not cache_path or payload.get("force_synthetic"):
        return {
            "ok": True,
            "mode": "synthetic_deferred",
            "metrics": {
                "total_return": None,
                "final_nav": initial_nav,
                "note": "parent should run synthetic_weight_nav",
            },
            "weights_count": len(weights_records),
        }

    try:
        import pandas as pd
        import qlib
        from qlib.backtest import backtest as qlib_backtest
    except ImportError as exc:
        return {
            "ok": True,
            "mode": "qlib_unavailable",
            "metrics": {
                "total_return": None,
                "final_nav": initial_nav,
                "note": f"pyqlib missing: {exc}",
            },
            "weights_count": len(weights_records),
        }

    # 进程内唯一 init
    qlib.init(provider_uri=cache_path, region=str(spec.get("region") or "cn"))

    from app.services.research_data.backtest_qlib.weight_strategy import (
        QuantDingerWeightStrategy,
    )
    from app.services.research_data.backtest_qlib.config_builder import (
        build_backtest_config,
    )
    from app.services.research_data.backtest.request import BacktestRequest
    from app.services.research_data.backtest.policy import (
        BacktestMarketPricePolicy,
        CostPolicy,
        ExecutionPolicy,
        TradingRule,
    )

    idx = []
    vals = []
    for r in weights_records:
        idx.append((pd.Timestamp(r["datetime"]), str(r["instrument"])))
        vals.append(float(r["weight"]))
    weights = pd.Series(
        vals, index=pd.MultiIndex.from_tuples(idx, names=["datetime", "instrument"])
    )

    strategy = QuantDingerWeightStrategy(
        target_weights=weights,
        risk_degree=float(strategy_cfg.get("risk_degree") or 1.0),
    )
    instruments = sorted({str(i) for i in weights.index.get_level_values("instrument")})
    if instruments:
        exchange_kwargs["codes"] = instruments

    req = BacktestRequest(
        experiment_id="qlib_strategy_worker",
        dataset_hash=str(payload.get("materialization_id") or "worker"),
        strategy_version="qlib_strategy_adapter@1",
        start_date=start,
        end_date=end,
        initial_capital=initial_nav,
        engine="qlib",
        execution_policy=ExecutionPolicy.model_validate(
            payload.get("execution_policy") or {}
        ),
        market_price_policy=BacktestMarketPricePolicy.model_validate(
            payload.get("market_price_policy") or {}
        ),
        cost_policy=CostPolicy.model_validate(payload.get("cost_policy") or {}),
        trading_rule=TradingRule.model_validate(payload.get("trading_rule") or {}),
    )
    config = build_backtest_config(
        req, strategy=strategy, exchange_kwargs=exchange_kwargs
    )
    portfolio_metric_dict, indicator_dict = qlib_backtest(**config)
    from app.services.research_data.backtest_qlib.result_mapper import map_qlib_outputs

    mapped = map_qlib_outputs(portfolio_metric_dict, indicator_dict)
    metrics = mapped.get("metrics") or {}
    if hasattr(metrics, "model_dump"):
        metrics = metrics.model_dump(mode="json")
    return {
        "ok": True,
        "mode": "qlib_backtest",
        "metrics": metrics if isinstance(metrics, dict) else {},
        "weights_count": len(weights_records),
    }


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) < 2:
        print("usage: worker_main.py <payload.json> <result.json>", file=sys.stderr)
        return 2
    return run_worker(args[0], args[1])


if __name__ == "__main__":
    raise SystemExit(main())
