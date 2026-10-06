"""构建回测 payload；合成路径用于无 pyqlib / force_inprocess。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

import pandas as pd

from .execution_adapter import build_exchange_kwargs, resolve_execution_bundle
from .protocol import QlibStrategySpec
from .strategy_adapter import build_weight_strategy_config


def build_worker_payload(
    spec: QlibStrategySpec,
    *,
    weights: pd.Series,
    cache_path: str = "",
    materialization_id: str = "",
) -> dict[str, Any]:
    """子进程输入：策略权重 + exchange + cache。"""
    execution, price, cost, rules = resolve_execution_bundle(spec)
    return {
        "spec": {
            "strategy_hash": spec.strategy_hash,
            "start_date": spec.start_date.isoformat(),
            "end_date": spec.end_date.isoformat(),
            "initial_nav": float(spec.initial_nav),
            "realism": spec.realism,
            "market_rule": spec.market_rule,
            "region": spec.region,
            "execution_mode": spec.execution_policy.mode,
            "fill_field": spec.execution_policy.fill_field,
        },
        "cache_path": cache_path,
        "materialization_id": materialization_id,
        "strategy_config": build_weight_strategy_config(weights),
        "exchange_kwargs": build_exchange_kwargs(spec),
        "cost_policy": cost.model_dump(mode="json"),
        "trading_rule": rules.model_dump(mode="json"),
        "execution_policy": execution.model_dump(mode="json"),
        "market_price_policy": price.model_dump(mode="json"),
    }


def synthetic_weight_nav(
    weights: pd.Series,
    price_bars: list[dict[str, Any]] | Mapping[tuple[str, date], Mapping[str, float]],
    *,
    initial_nav: float,
    fill_field: str = "open",
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """无 Qlib 时的权重 NAV 摘要（GROSS 可比）；instrument 为 qlib 小写 id。"""
    from app.services.research_data.qlib_materializer.instrument_mapper import (
        to_qlib_instrument,
    )

    # 索引价格
    indexed: dict[tuple[str, date], dict[str, float]] = {}
    if isinstance(price_bars, Mapping) and price_bars:
        first = next(iter(price_bars.keys()))
        if isinstance(first, tuple):
            for (ik, d), bar in price_bars.items():
                try:
                    qid = to_qlib_instrument(str(ik)).lower()
                except Exception:
                    qid = str(ik).lower()
                dd = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
                indexed[(qid, dd)] = {
                    "open": float(bar.get("open", float("nan"))),
                    "close": float(bar.get("close", float("nan"))),
                }
        else:
            price_bars = list(price_bars.values())  # type: ignore[assignment]
    if not indexed:
        for row in price_bars:  # type: ignore[union-attr]
            ik = str(row["instrument_key"])
            try:
                qid = to_qlib_instrument(ik).lower()
            except Exception:
                qid = ik.lower()
            dd = date.fromisoformat(str(row["trading_date"])[:10])
            indexed[(qid, dd)] = {
                "open": float(row.get("open", float("nan"))),
                "close": float(row.get("close", float("nan"))),
            }

    dates = sorted({d for (_i, d) in indexed.keys()})
    if start:
        dates = [d for d in dates if d >= start]
    if end:
        dates = [d for d in dates if d <= end]
    if not dates:
        return {"total_return": None, "final_nav": initial_nav, "n_days": 0}

    # 按日权重（前向填充）
    w_by_day: dict[date, dict[str, float]] = {}
    if not weights.empty:
        for (dt, inst), w in weights.items():
            d = pd.Timestamp(dt).date()
            w_by_day.setdefault(d, {})[str(inst)] = float(w)

    nav = float(initial_nav)
    prev_close: dict[str, float] = {}
    last_w: dict[str, float] = {}
    rets: list[float] = []
    for i, d in enumerate(dates):
        if d in w_by_day:
            last_w = dict(w_by_day[d])
        # 日收益：持仓权重 × 标的 close-to-close；首日无收益
        if i > 0 and last_w:
            day_r = 0.0
            for inst, w in last_w.items():
                bar = indexed.get((inst, d))
                prev = prev_close.get(inst)
                if not bar or prev is None or prev <= 0:
                    continue
                c = float(bar.get("close", float("nan")))
                if c != c or c <= 0:
                    continue
                day_r += w * (c / prev - 1.0)
            nav = nav * (1.0 + day_r)
            rets.append(day_r)
        # 更新昨收
        for inst in set(last_w) | set(prev_close):
            bar = indexed.get((inst, d))
            if bar:
                c = float(bar.get("close", float("nan")))
                if c == c and c > 0:
                    prev_close[inst] = c
        _ = fill_field  # 合成路径用 close-to-close；fill 留给真实 Qlib

    total = nav / float(initial_nav) - 1.0 if initial_nav else None
    return {
        "total_return": total,
        "final_nav": nav,
        "n_days": len(dates),
        "n_return_days": len(rets),
        "mode": "synthetic_weight_nav",
    }
