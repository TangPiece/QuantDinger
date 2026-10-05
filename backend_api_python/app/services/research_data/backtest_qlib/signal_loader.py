"""从 Signal artifact 加载 TargetPosition → Qlib 权重 Series。

产出 MultiIndex ``(datetime, instrument)`` 的 ``target_weight`` Series；
``CNStock:xxx`` 经 ``to_qlib_instrument`` 后统一小写（与 Materializer 一致）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.services.research_data.contracts import ArtifactRecord
from app.services.research_data.qlib_materializer.instrument_mapper import (
    to_qlib_instrument,
)


class SignalLoadError(ValueError):
    """TargetPosition artifact 无法加载或格式非法。"""


def _resolve_positions_path(storage_uri: str) -> Path:
    """解析 artifact 目录下的 target_positions.parquet。"""
    root = Path(storage_uri)
    if root.is_file() and root.name.endswith(".parquet"):
        return root
    candidate = root / "target_positions.parquet"
    if candidate.is_file():
        return candidate
    raise SignalLoadError(f"target_positions.parquet not found under {storage_uri!r}")


def load_target_weight_series(
    artifact: ArtifactRecord,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.Series:
    """读取 TargetPosition parquet，映射为 Qlib instrument 权重 Series。

    Args:
        artifact: Registry ArtifactRecord（type=signal，含 storage_uri）
        start_date / end_date: 可选日期裁剪（含端点，ISO 日期字符串）

    Returns:
        MultiIndex (datetime, instrument) → float weight；instrument 为小写 qlib id。

    语义：同一日多行权重保留；零权重行保留（策略侧用于清空）。
    """
    path = _resolve_positions_path(artifact.storage_uri)
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(path)
        df = table.to_pandas()
    except Exception as exc:
        raise SignalLoadError(f"failed to read {path}: {exc}") from exc

    required = {"instrument_key", "trading_date", "target_weight"}
    missing = required - set(df.columns)
    if missing:
        raise SignalLoadError(f"target_positions missing columns: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        weight = row["target_weight"]
        if weight is None or (isinstance(weight, float) and pd.isna(weight)):
            continue
        ik = str(row["instrument_key"])
        try:
            qlib_id = to_qlib_instrument(ik).lower()
        except Exception as exc:
            raise SignalLoadError(f"instrument map failed for {ik!r}: {exc}") from exc
        dt = pd.Timestamp(str(row["trading_date"]))
        rows.append(
            {
                "datetime": dt.normalize(),
                "instrument": qlib_id,
                "target_weight": float(weight),
            }
        )

    if not rows:
        raise SignalLoadError("no usable target_weight rows in artifact")

    out = pd.DataFrame(rows)
    if start_date:
        out = out[out["datetime"] >= pd.Timestamp(start_date).normalize()]
    if end_date:
        out = out[out["datetime"] <= pd.Timestamp(end_date).normalize()]
    if out.empty:
        raise SignalLoadError("target weights empty after date filter")

    series = out.set_index(["datetime", "instrument"])["target_weight"].sort_index()
    # 同日同标的多行取末值（artifact 正常应唯一）
    if series.index.duplicated().any():
        series = series[~series.index.duplicated(keep="last")]
    return series.astype(float)


def weights_for_date(series: pd.Series, trade_date: pd.Timestamp) -> dict[str, float] | None:
    """取某交易日目标权重 dict；缺省日返回 None（策略不调仓）。"""
    day = pd.Timestamp(trade_date).normalize()
    if not isinstance(series.index, pd.MultiIndex):
        raise SignalLoadError("target weight series must be MultiIndex")
    try:
        day_slice = series.xs(day, level="datetime")
    except KeyError:
        return None
    if isinstance(day_slice, pd.Series):
        return {str(k): float(v) for k, v in day_slice.items()}
    # 极端：单值标量（不应出现于标准 MultiIndex）
    return None
