"""Signal artifact → 按日 TargetPosition（Domain instrument_key，不经 qlib）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping

from app.services.research_data.contracts import ArtifactRecord, TargetPosition


class SignalLoadError(ValueError):
    """TargetPosition artifact 无法加载。"""


def _resolve_positions_path(storage_uri: str) -> Path:
    root = Path(storage_uri)
    if root.is_file() and root.name.endswith(".parquet"):
        return root
    candidate = root / "target_positions.parquet"
    if candidate.is_file():
        return candidate
    raise SignalLoadError(f"target_positions.parquet not found under {storage_uri!r}")


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_targets_by_date(
    artifact: ArtifactRecord,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, list[TargetPosition]]:
    """读取 target_positions.parquet，按 trading_date(ISO) 分组。

    Returns:
        ``{ "YYYY-MM-DD": [TargetPosition, ...] }``
    """
    path = _resolve_positions_path(artifact.storage_uri)
    try:
        import pyarrow.parquet as pq

        df = pq.read_table(path).to_pandas()
    except Exception as exc:
        raise SignalLoadError(f"failed to read {path}: {exc}") from exc

    required = {"instrument_key", "trading_date"}
    missing = required - set(df.columns)
    if missing:
        raise SignalLoadError(f"missing columns: {sorted(missing)}")

    start = date.fromisoformat(start_date[:10]) if start_date else None
    end = date.fromisoformat(end_date[:10]) if end_date else None
    by_day: dict[str, list[TargetPosition]] = defaultdict(list)

    for _, row in df.iterrows():
        td = row["trading_date"]
        if hasattr(td, "isoformat"):
            day = td if isinstance(td, date) and not isinstance(td, datetime) else (
                td.date() if isinstance(td, datetime) else date.fromisoformat(str(td)[:10])
            )
        else:
            day = date.fromisoformat(str(td)[:10])
        if start and day < start:
            continue
        if end and day > end:
            continue

        tw = row["target_weight"] if "target_weight" in df.columns else None
        tq = row["target_quantity"] if "target_quantity" in df.columns else None
        if tw is not None and hasattr(tw, "__float__"):
            try:
                import math

                if isinstance(tw, float) and math.isnan(tw):
                    tw = None
            except Exception:
                pass
        ts_raw = row["timestamp"] if "timestamp" in df.columns else None
        ts = _parse_ts(ts_raw) if ts_raw is not None and str(ts_raw) not in ("", "None", "NaT") else datetime(
            day.year, day.month, day.day, 15, 0, 0, tzinfo=timezone.utc
        )

        by_day[day.isoformat()].append(
            TargetPosition(
                instrument_key=str(row["instrument_key"]),
                trading_date=day.isoformat(),
                portfolio_id=str(row["portfolio_id"]) if "portfolio_id" in df.columns and row.get("portfolio_id") is not None else "default",
                strategy_version=str(row["strategy_version"]) if "strategy_version" in df.columns and row.get("strategy_version") is not None else "",
                dataset_hash=str(row["dataset_hash"]) if "dataset_hash" in df.columns and row.get("dataset_hash") is not None else "",
                timestamp=ts,
                target_weight=float(tw) if tw is not None else None,
                target_quantity=float(tq) if tq is not None and str(tq) not in ("", "None", "nan") else None,
                signal_id=str(row["signal_id"]) if "signal_id" in df.columns and row.get("signal_id") is not None else None,
            )
        )
    return dict(by_day)


def targets_for_day(
    by_date: Mapping[str, list[TargetPosition]],
    trading_date: str | date,
) -> list[TargetPosition]:
    """取某日目标；缺省返回空列表（当日不调仓）。"""
    key = trading_date.isoformat() if isinstance(trading_date, date) else str(trading_date)[:10]
    return list(by_date.get(key) or [])
