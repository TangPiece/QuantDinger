"""TargetPosition → Qlib weight Series（不改变 QD Portfolio 语义）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

import pandas as pd

from app.services.research_data.qlib_materializer.instrument_mapper import (
    to_qlib_instrument,
)

from .protocol import StrategyPlan


def targets_to_weight_series(
    targets_by_date: Mapping[date, Sequence[Mapping[str, Any]]]
    | Sequence[Mapping[str, Any]],
    *,
    start: date | None = None,
    end: date | None = None,
) -> pd.Series:
    """5A TargetPosition → MultiIndex (datetime, instrument) weight Series。"""
    rows_iter: list[Mapping[str, Any]]
    if isinstance(targets_by_date, Mapping):
        rows_iter = []
        for d, rows in targets_by_date.items():
            for r in rows:
                item = dict(r)
                item.setdefault("trading_date", d)
                rows_iter.append(item)
    else:
        rows_iter = list(targets_by_date)

    records: list[dict[str, Any]] = []
    for r in rows_iter:
        w = r.get("target_weight", r.get("weight"))
        if w is None:
            continue
        try:
            wf = float(w)
        except (TypeError, ValueError):
            continue
        if wf != wf:
            continue
        ik = str(r.get("instrument_key") or "")
        if not ik:
            continue
        try:
            qlib_id = to_qlib_instrument(ik).lower()
        except Exception:
            continue
        td = r.get("trading_date")
        dt = pd.Timestamp(str(td)[:10]).normalize()
        d = dt.date()
        if start and d < start:
            continue
        if end and d > end:
            continue
        records.append({"datetime": dt, "instrument": qlib_id, "weight": wf})

    if not records:
        return pd.Series(dtype=float)
    df = pd.DataFrame(records).drop_duplicates(
        subset=["datetime", "instrument"], keep="last"
    )
    df = df.set_index(["datetime", "instrument"]).sort_index()
    return df["weight"]


def build_strategy_plan() -> StrategyPlan:
    """v1 固定 WeightStrategy 计划（禁用原生 TopK 重选）。"""
    return StrategyPlan(
        strategy_kind="WEIGHT_FROM_TARGET_POSITION",
        weight_method="FROM_TARGET_POSITION",
        rebalance_note="HOLD_UNTIL_NEXT_REBALANCE",
        native_topk_enabled=False,
    )


def weights_close_to(a: pd.Series, b: pd.Series, *, tol: float = 1e-9) -> bool:
    """权重 Series 公共索引对齐。"""
    if a.empty and b.empty:
        return True
    common = a.index.intersection(b.index)
    if len(common) == 0:
        return False
    return bool((a.loc[common] - b.loc[common]).abs().max() <= tol)
