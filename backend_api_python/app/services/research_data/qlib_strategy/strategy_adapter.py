"""组装 WeightStrategy 配置（不导入 qlib.strategy）。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .portfolio_adapter import build_strategy_plan
from .protocol import StrategyPlan


def build_weight_strategy_config(
    weights: pd.Series,
    *,
    risk_degree: float = 1.0,
) -> dict[str, Any]:
    """序列化可传入子进程的策略配置（不含 qlib 对象）。"""
    plan = build_strategy_plan()
    # MultiIndex → 可 JSON 化记录
    records: list[dict[str, Any]] = []
    if not weights.empty:
        for (dt, inst), w in weights.items():
            records.append(
                {
                    "datetime": str(pd.Timestamp(dt).date()),
                    "instrument": str(inst),
                    "weight": float(w),
                }
            )
    return {
        "strategy_kind": plan.strategy_kind,
        "risk_degree": float(risk_degree),
        "weights": records,
        "plan": plan.model_dump(mode="json"),
    }


def strategy_plan() -> StrategyPlan:
    return build_strategy_plan()
