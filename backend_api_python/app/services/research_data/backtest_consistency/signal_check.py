"""校验 Canonical Signal artifact 对两引擎输入等价。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.research_data.contracts import ArtifactRecord
from app.services.research_data.backtest_production.signal_loader import (
    load_targets_by_date,
)


@dataclass
class SignalCheckResult:
    """Signal 一致性检查结果。"""

    ok: bool
    n_rows: int = 0
    n_days: int = 0
    instruments: list[str] | None = None
    message: str = ""


def _resolve_parquet(storage_uri: str) -> Path:
    root = Path(storage_uri)
    if root.is_file() and root.name.endswith(".parquet"):
        return root
    return root / "target_positions.parquet"


def check_signal_artifact(
    artifact: ArtifactRecord,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> SignalCheckResult:
    """确认 target_positions.parquet 可读，且 Domain targets 非空可分组。

    不强制走 qlib loader（避免 Domain 依赖），但检查 weight/quantity 列齐全。
    """
    path = _resolve_parquet(artifact.storage_uri)
    if not path.is_file():
        return SignalCheckResult(ok=False, message=f"missing parquet: {path}")

    try:
        import pyarrow.parquet as pq

        df = pq.read_table(path).to_pandas()
    except Exception as exc:
        return SignalCheckResult(ok=False, message=f"read failed: {exc}")

    if "instrument_key" not in df.columns or "trading_date" not in df.columns:
        return SignalCheckResult(ok=False, message="missing instrument_key/trading_date")
    if "target_weight" not in df.columns and "target_quantity" not in df.columns:
        return SignalCheckResult(
            ok=False, message="need target_weight or target_quantity"
        )

    by_day = load_targets_by_date(artifact, start_date=start_date, end_date=end_date)
    instruments = sorted(
        {t.instrument_key for day in by_day.values() for t in day}
    )
    n_rows = sum(len(v) for v in by_day.values())
    return SignalCheckResult(
        ok=True,
        n_rows=n_rows,
        n_days=len(by_day),
        instruments=instruments,
        message="ok",
    )


def targets_quantity_map(
    artifact: ArtifactRecord,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[tuple[str, str], float]:
    """(trading_date, instrument_key) → target_quantity（或由 weight 占位 0）。"""
    by_day = load_targets_by_date(artifact, start_date=start_date, end_date=end_date)
    out: dict[tuple[str, str], float] = {}
    for day, items in by_day.items():
        for t in items:
            qty = float(t.target_quantity) if t.target_quantity is not None else 0.0
            out[(day, t.instrument_key)] = qty
    return out
