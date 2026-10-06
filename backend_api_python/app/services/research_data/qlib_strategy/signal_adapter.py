"""QuantDinger Signal / score → Qlib Prediction Series。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

import pandas as pd

from app.services.research_data.qlib_materializer.instrument_mapper import (
    to_qlib_instrument,
)


def to_prediction_series(
    rows: Sequence[Mapping[str, Any]],
    *,
    score_field: str = "score",
    start: date | None = None,
    end: date | None = None,
) -> pd.Series:
    """将 Signal/score 行转为 MultiIndex (datetime, instrument) → score。

    instrument 经 ``to_qlib_instrument`` 后小写，与 Materializer 一致。
    """
    records: list[dict[str, Any]] = []
    for r in rows:
        raw_score = r.get(score_field, r.get("value"))
        if raw_score is None:
            continue
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if score != score:
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
        records.append({"datetime": dt, "instrument": qlib_id, "score": score})
    if not records:
        return pd.Series(dtype=float)
    df = pd.DataFrame(records).drop_duplicates(
        subset=["datetime", "instrument"], keep="last"
    )
    df = df.set_index(["datetime", "instrument"]).sort_index()
    return df["score"]


def prediction_close_to(
    a: pd.Series, b: pd.Series, *, tol: float = 1e-9
) -> bool:
    """两 Prediction Series 在公共索引上是否对齐。"""
    if a.empty and b.empty:
        return True
    common = a.index.intersection(b.index)
    if len(common) == 0:
        return False
    return bool((a.loc[common] - b.loc[common]).abs().max() <= tol)
