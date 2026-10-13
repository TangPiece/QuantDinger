"""Local staging / marker / factor cache paths for fund_cn (not l2_daily prefix)."""

from __future__ import annotations

import os
from pathlib import Path

from .catalog import FACTOR_SET, FACTOR_SET_VERSION


def backend_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_staging_root() -> Path:
    raw = os.getenv("FUND_CN_STAGING_ROOT", "").strip()
    if raw:
        path = Path(raw)
    else:
        path = backend_root() / "data" / "fundamental_staging" / "fund_cn"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_factor_root() -> Path:
    """Local hot cache of published daily factor panels (mirrors R2 logical tree)."""
    raw = os.getenv("FUND_CN_FACTOR_ROOT", "").strip()
    if raw:
        path = Path(raw)
    else:
        path = backend_root() / "data" / "fundamental_staging" / "factors" / "fund_cn"
    path.mkdir(parents=True, exist_ok=True)
    return path


def markers_dir(root: Path | None = None) -> Path:
    path = (root or default_staging_root()) / "_markers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def statements_dir(root: Path | None = None) -> Path:
    path = (root or default_staging_root()) / "statements"
    path.mkdir(parents=True, exist_ok=True)
    return path


def announce_dir(root: Path | None = None) -> Path:
    path = (root or default_staging_root()) / "announce"
    path.mkdir(parents=True, exist_ok=True)
    return path


def share_capital_dir(root: Path | None = None) -> Path:
    path = (root or default_staging_root()) / "share_capital"
    path.mkdir(parents=True, exist_ok=True)
    return path


def factor_set_segment() -> str:
    return FACTOR_SET


def local_factor_day_path(root: Path, trading_date: str) -> Path:
    """YYYY-MM-DD or YYYYMMDD → local mirror of qd/factor layout."""
    day = str(trading_date).replace("-", "")
    yyyy, yyyymm = day[:4], day[:6]
    folder = root / FACTOR_SET_VERSION / yyyy / yyyymm
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{day}.parquet"


def r2_factor_set() -> str:
    return FACTOR_SET
