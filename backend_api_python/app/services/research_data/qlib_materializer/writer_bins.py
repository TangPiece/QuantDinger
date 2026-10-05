"""写出 Qlib 兼容目录：calendars / instruments / features/*.day.bin。

Qlib FileFeatureStorage 格式：
  .day.bin = little-endian float32
  [0] = start_index（相对 calendars/day.txt）
  [1:] = feature values
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .calendar import write_calendar_day_txt
from .instrument_mapper import to_qlib_instrument


def write_instruments_txt(
    path: Path,
    qlib_instruments: Sequence[str],
    *,
    start: date,
    end: date,
) -> None:
    """Qlib instruments 文件：小写 instrument\\tstart\\tend。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    # Qlib 惯例：instruments 与 features/ 目录均为小写
    for inst in sorted({str(x).lower() for x in qlib_instruments}):
        lines.append(f"{inst}\t{start.isoformat()}\t{end.isoformat()}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _align_series(
    market: pd.DataFrame,
    *,
    instrument_key: str,
    field: str,
    calendar: Sequence[date],
) -> np.ndarray:
    """按完整 calendar 对齐；缺失保持 NaN（禁止填 0）。"""
    cal_index = pd.Index([pd.Timestamp(d) for d in calendar])
    part = market[market["instrument_key"] == instrument_key].copy()
    if part.empty or field not in part.columns:
        return np.full(len(calendar), np.nan, dtype=np.float32)
    part["trading_date"] = pd.to_datetime(part["trading_date"])
    part = part.drop_duplicates(subset=["trading_date"], keep="last")
    part = part.set_index("trading_date").reindex(cal_index)
    values = pd.to_numeric(part[field], errors="coerce").to_numpy(dtype=np.float64)
    return values.astype(np.float32)


def encode_qlib_day_bin(values: np.ndarray, *, start_index: int = 0) -> np.ndarray:
    """编码 Qlib day.bin：首元素为 calendar start_index，其后为特征值。"""
    payload = np.hstack([np.array([float(start_index)], dtype=np.float32), values.astype(np.float32)])
    return payload.astype("<f4")


def write_feature_bins(
    features_root: Path,
    market: pd.DataFrame,
    *,
    instrument_keys: Sequence[str],
    fields: Sequence[str],
    calendar: Sequence[date],
    start_index: int = 0,
) -> int:
    """写入 features/{qlib_lower}/{field}.day.bin，返回写出文件数。"""
    features_root.mkdir(parents=True, exist_ok=True)
    written = 0
    for ik in instrument_keys:
        qlib_id = to_qlib_instrument(ik)
        inst_dir = features_root / qlib_id.lower()
        inst_dir.mkdir(parents=True, exist_ok=True)
        for field in fields:
            arr = _align_series(market, instrument_key=ik, field=field, calendar=calendar)
            bin_path = inst_dir / f"{field}.day.bin"
            encode_qlib_day_bin(arr, start_index=start_index).tofile(str(bin_path))
            written += 1
    return written


def dump_qlib_dataset(
    cache_path: Path,
    market: pd.DataFrame,
    *,
    instrument_keys: Sequence[str],
    fields: Sequence[str],
    calendar: Sequence[date],
    instruments_name: str = "all",
) -> dict[str, int]:
    """落盘完整 Qlib provider 目录结构。"""
    if not calendar:
        raise ValueError("calendar is empty; cannot materialize Qlib cache")
    write_calendar_day_txt(cache_path / "calendars" / "day.txt", calendar)
    qlib_ids = [to_qlib_instrument(ik) for ik in instrument_keys]
    write_instruments_txt(
        cache_path / "instruments" / f"{instruments_name}.txt",
        qlib_ids,
        start=calendar[0],
        end=calendar[-1],
    )
    n_bins = write_feature_bins(
        cache_path / "features",
        market,
        instrument_keys=instrument_keys,
        fields=fields,
        calendar=calendar,
        start_index=0,
    )
    return {
        "calendar_count": len(calendar),
        "instrument_count": len(set(x.lower() for x in qlib_ids)),
        "feature_file_count": n_bins,
        "row_count": int(len(calendar) * len(set(instrument_keys))),
    }
