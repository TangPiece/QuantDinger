"""从 5A/5B/5D 产物或内存帧加载 Diff 输入。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.services.research_data.contracts import (
    QlibRunSummary,
    ResearchBacktestSummary,
    StrategyResearchSummary,
)
from app.services.research_data.qlib_materializer.instrument_mapper import (
    to_qlib_instrument,
)
from app.services.research_data.qlib_strategy import (
    targets_to_weight_series,
    to_prediction_series,
)


def normalize_instrument(key: str) -> str:
    """统一为 qlib 小写 instrument id。"""
    text = str(key or "").strip()
    if not text:
        return ""
    try:
        return to_qlib_instrument(text).lower()
    except Exception:
        return text.lower()


def load_qlib_nav_curve(storage_uri: str) -> list[dict[str, Any]]:
    """读 qlib_run/.../nav/daily.json。"""
    path = Path(storage_uri) / "nav" / "daily.json"
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return list(raw.get("nav_curve") or [])


def load_qlib_weights(storage_uri: str) -> list[dict[str, Any]]:
    path = Path(storage_uri) / "weights" / "weights.json"
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")))


def load_qlib_predictions(storage_uri: str) -> list[dict[str, Any]]:
    path = Path(storage_uri) / "prediction" / "scores.json"
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")))


def qd_nav_from_frames(nav_points: Sequence[Any]) -> list[dict[str, Any]]:
    """BacktestFrames.nav → 统一曲线。"""
    out: list[dict[str, Any]] = []
    for p in nav_points:
        if hasattr(p, "trading_date"):
            td = p.trading_date
            nav = float(p.nav)
        else:
            td = p.get("trading_date")
            nav = float(p.get("nav"))
        out.append(
            {
                "trading_date": str(td)[:10],
                "nav": nav,
                "portfolio_return": getattr(p, "portfolio_return", None)
                if not isinstance(p, dict)
                else p.get("portfolio_return"),
            }
        )
    return out


def qd_nav_from_storage(storage_uri: str) -> list[dict[str, Any]]:
    """尽力从 backtest 目录读 portfolio parquet / 回退空。"""
    root = Path(storage_uri)
    # 优先：若有导出的 nav json（测试可注入）
    nav_json = root / "nav" / "daily.json"
    if nav_json.is_file():
        raw = json.loads(nav_json.read_text(encoding="utf-8"))
        return list(raw.get("nav_curve") or raw.get("nav") or [])
    # parquet panels：按年/月扫
    portfolio = root / "portfolio"
    if not portfolio.is_dir():
        return []
    try:
        import pyarrow.parquet as pq
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for part in sorted(portfolio.rglob("part-*.parquet")):
        try:
            table = pq.read_table(part)
            for r in table.to_pylist():
                rows.append(
                    {
                        "trading_date": str(r.get("trading_date"))[:10],
                        "nav": float(r.get("nav")),
                        "portfolio_return": None,
                    }
                )
        except Exception:
            continue
    rows.sort(key=lambda x: x["trading_date"])
    return rows


def signal_rows_from_meta_or_series(
    meta: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if meta.get("signal_rows") is not None:
        return list(meta["signal_rows"])
    return []


def build_weight_records(
    targets_by_date: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    """TargetPosition → 与 Qlib weights.json 同形记录。"""
    import pandas as pd

    if not targets_by_date:
        return []
    series = targets_to_weight_series(targets_by_date, start=start, end=end)
    out: list[dict[str, Any]] = []
    for (dt, inst), w in series.items():
        out.append(
            {
                "datetime": str(pd.Timestamp(dt).date()),
                "instrument": str(inst),
                "weight": float(w),
            }
        )
    return out


def build_prediction_records(
    signal_rows: Sequence[Mapping[str, Any]],
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    series = to_prediction_series(signal_rows, start=start, end=end)
    import pandas as pd

    out: list[dict[str, Any]] = []
    for (dt, inst), score in series.items():
        out.append(
            {
                "datetime": str(pd.Timestamp(dt).date()),
                "instrument": str(inst),
                "score": float(score),
            }
        )
    return out


def strategy_identity(
    strategy: StrategyResearchSummary | None,
    *,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """抽取 Dataset/Universe 身份字段。"""
    meta = meta or {}
    if strategy is None:
        return {
            "factor_dataset_id": str(meta.get("factor_dataset_id") or meta.get("dataset_ref") or ""),
            "universe_code": str(meta.get("universe_code") or "UNIVERSE_INJECTED"),
            "snapshot_id": str(meta.get("snapshot_id") or "SNAP_INJECTED"),
            "dataset_ref": str(meta.get("dataset_ref") or ""),
            "materialization_id": str(meta.get("materialization_id") or ""),
            "dataset_hash": str(meta.get("dataset_hash") or ""),
        }
    return {
        "factor_dataset_id": strategy.factor_dataset_id or "",
        "universe_code": strategy.universe_code or "",
        "snapshot_id": strategy.snapshot_id or "",
        "dataset_ref": str(meta.get("dataset_ref") or strategy.factor_dataset_id or ""),
        "materialization_id": str(meta.get("materialization_id") or ""),
        "dataset_hash": str(meta.get("dataset_hash") or ""),
    }


def summarize_bars(bars: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """注入 bars 的 Dataset 摘要统计。"""
    if not bars:
        return {"n_rows": 0, "instruments": [], "dates": [], "has_nan": False, "has_inf": False}
    instruments: set[str] = set()
    dates: set[str] = set()
    has_nan = False
    has_inf = False
    for r in bars:
        instruments.add(normalize_instrument(str(r.get("instrument_key") or "")))
        dates.add(str(r.get("trading_date"))[:10])
        for k in ("open", "high", "low", "close", "volume"):
            if k not in r:
                continue
            try:
                v = float(r[k])
            except (TypeError, ValueError):
                has_nan = True
                continue
            if v != v:
                has_nan = True
            if v == float("inf") or v == float("-inf"):
                has_inf = True
    return {
        "n_rows": len(bars),
        "n_instruments": len(instruments),
        "instruments": sorted(instruments),
        "date_min": min(dates) if dates else "",
        "date_max": max(dates) if dates else "",
        "n_dates": len(dates),
        "has_nan": has_nan,
        "has_inf": has_inf,
    }


__all__ = [
    "QlibRunSummary",
    "ResearchBacktestSummary",
    "StrategyResearchSummary",
    "build_prediction_records",
    "build_weight_records",
    "load_qlib_nav_curve",
    "load_qlib_predictions",
    "load_qlib_weights",
    "normalize_instrument",
    "qd_nav_from_frames",
    "qd_nav_from_storage",
    "signal_rows_from_meta_or_series",
    "strategy_identity",
    "summarize_bars",
]
