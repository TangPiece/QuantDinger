"""本地日/月 Parquet 与 R2 按日备份。storage_uri 只存逻辑键。"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from .catalog import FACTOR_VERSION, factor_ids, wide_columns

_log = logging.getLogger(__name__)
_uploader = None
_client = None


def set_r2_uploader(uploader) -> None:
    """测试注入：``uploader(logical_key: str, payload: bytes)``。"""
    global _uploader
    _uploader = uploader


def default_root() -> Path:
    raw = os.getenv("LEVEL2_L2_DAILY_ROOT", "").strip()
    if raw:
        path = Path(raw)
        path.mkdir(parents=True, exist_ok=True)
        return path
    # level2_factors/l2_daily/storage.py → backend_api_python
    root = Path(__file__).resolve().parents[4] / "data" / "level2_staging" / "factors" / "l2_daily"
    root.mkdir(parents=True, exist_ok=True)
    return root


def r2_prefix() -> str:
    return os.getenv("R2_L2_DAILY_PREFIX", "factors/l2_daily").strip().strip("/") or "factors/l2_daily"


def logical_day_key(trade_date: str, *, factor_version: int = FACTOR_VERSION) -> str:
    day = str(trade_date)
    return (
        f"{r2_prefix()}/version={factor_version}/"
        f"year={day[:4]}/month={day[:6]}/date={day}.parquet"
    )


def logical_status_key(trade_date: str, *, factor_version: int = FACTOR_VERSION) -> str:
    day = str(trade_date)
    return (
        f"{r2_prefix()}/version={factor_version}/"
        f"year={day[:4]}/month={day[:6]}/date={day}.status.parquet"
    )


def month_dir(root: Path, trade_date: str, *, factor_version: int = FACTOR_VERSION) -> Path:
    day = str(trade_date)
    path = root / f"version={factor_version}" / f"year={day[:4]}" / f"month={day[:6]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def day_path(root: Path, trade_date: str, *, factor_version: int = FACTOR_VERSION) -> Path:
    return month_dir(root, trade_date, factor_version=factor_version) / f"date={trade_date}.parquet"


def status_path(root: Path, trade_date: str, *, factor_version: int = FACTOR_VERSION) -> Path:
    return month_dir(root, trade_date, factor_version=factor_version) / f"date={trade_date}.status.parquet"


def month_part_path(root: Path, yyyymm: str, *, factor_version: int = FACTOR_VERSION) -> Path:
    return (
        root
        / f"version={factor_version}"
        / f"year={yyyymm[:4]}"
        / f"month={yyyymm}"
        / "part-000.parquet"
    )


def read_day(root: Path, trade_date: str, *, factor_version: int = FACTOR_VERSION) -> pd.DataFrame | None:
    path = day_path(root, trade_date, factor_version=factor_version)
    if not path.is_file():
        return None
    return pd.read_parquet(path)


def write_day(
    root: Path,
    trade_date: str,
    frame: pd.DataFrame,
    *,
    factor_version: int = FACTOR_VERSION,
) -> Path:
    """原子写入日宽表，补齐缺失因子列。"""
    columns = wide_columns()
    panel = frame.copy()
    if "trade_date" not in panel.columns:
        panel["trade_date"] = str(trade_date)
    if "symbol" not in panel.columns:
        raise ValueError("frame 缺少 symbol")
    for column in columns:
        if column not in panel.columns:
            panel[column] = float("nan")
    panel = panel[columns]
    destination = day_path(root, trade_date, factor_version=factor_version)
    temporary = destination.with_suffix(".parquet.tmp")
    panel.to_parquet(temporary, index=False)
    temporary.replace(destination)
    return destination


def merge_group_columns(
    existing: pd.DataFrame | None,
    rows: list[dict],
    group_columns: list[str],
    trade_date: str,
) -> pd.DataFrame:
    """按 symbol 合并一组新列到日宽表。"""
    incoming = pd.DataFrame(rows)
    if incoming.empty:
        if existing is not None:
            return existing
        empty = pd.DataFrame(columns=wide_columns())
        return empty
    incoming["trade_date"] = str(trade_date)
    keep = ["trade_date", "symbol", *group_columns]
    for column in keep:
        if column not in incoming.columns and column not in ("trade_date", "symbol"):
            incoming[column] = float("nan")
    incoming = incoming[[c for c in keep if c in incoming.columns]]

    if existing is None or existing.empty:
        base = incoming
    else:
        base = existing.drop(columns=[c for c in group_columns if c in existing.columns], errors="ignore")
        base = base.merge(incoming, on=["trade_date", "symbol"], how="outer")
    for column in wide_columns():
        if column not in base.columns:
            base[column] = float("nan")
    return base[wide_columns()]


def write_status(
    root: Path,
    trade_date: str,
    status_rows: list[dict],
    *,
    factor_version: int = FACTOR_VERSION,
) -> Path:
    """写入/合并逐股×组状态。"""
    path = status_path(root, trade_date, factor_version=factor_version)
    frame = pd.DataFrame(status_rows)
    if path.is_file() and not frame.empty:
        old = pd.read_parquet(path)
        # 同 symbol+group 覆盖
        key = ["symbol", "factor_group"]
        old = old.set_index(key)
        frame = frame.set_index(key)
        old.update(frame)
        combined = pd.concat([old, frame[~frame.index.isin(old.index)]])
        frame = combined.reset_index()
    elif frame.empty and path.is_file():
        return path
    temporary = path.with_suffix(".parquet.tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)
    return path


def upload_day_to_r2(root: Path, trade_date: str, *, factor_version: int = FACTOR_VERSION) -> str | None:
    """上传日宽表到 R2，返回逻辑 storage_uri。未配置时返回逻辑键但不上传。"""
    path = day_path(root, trade_date, factor_version=factor_version)
    if not path.is_file():
        return None
    key = logical_day_key(trade_date, factor_version=factor_version)
    payload = path.read_bytes()
    if _uploader is not None:
        _uploader(key, payload)
        return key
    if not _r2_configured():
        return key
    try:
        _r2_client().put_object(Bucket=_bucket(), Key=key, Body=payload)
    except Exception:
        _log.warning("l2_daily R2 上传失败 %s", trade_date, exc_info=True)
        return key
    return key


def compact_month(
    root: Path,
    yyyymm: str,
    *,
    factor_version: int = FACTOR_VERSION,
    delete_days: bool = False,
) -> Path | None:
    """合并当月全部 date=*.parquet 为 part-000.parquet。"""
    directory = root / f"version={factor_version}" / f"year={yyyymm[:4]}" / f"month={yyyymm}"
    if not directory.is_dir():
        return None
    parts = sorted(directory.glob("date=????????.parquet"))
    if not parts:
        return None
    frames = [pd.read_parquet(path) for path in parts]
    panel = pd.concat(frames, ignore_index=True)
    for column in wide_columns():
        if column not in panel.columns:
            panel[column] = float("nan")
    panel = panel[wide_columns()]
    destination = month_part_path(root, yyyymm, factor_version=factor_version)
    temporary = destination.with_suffix(".parquet.tmp")
    panel.to_parquet(temporary, index=False)
    temporary.replace(destination)
    if delete_days:
        for path in parts:
            path.unlink(missing_ok=True)
    return destination


def list_local_day_files(root: Path, yyyymm: str, *, factor_version: int = FACTOR_VERSION) -> list[str]:
    directory = root / f"version={factor_version}" / f"year={yyyymm[:4]}" / f"month={yyyymm}"
    if not directory.is_dir():
        return []
    dates = []
    for path in directory.glob("date=????????.parquet"):
        stem = path.name[len("date=") : -len(".parquet")]
        if len(stem) == 8 and stem.isdigit():
            dates.append(stem)
    return sorted(dates)


def _r2_configured() -> bool:
    return bool(
        os.getenv("R2_ENDPOINT_URL", "").strip()
        and os.getenv("R2_ACCESS_KEY_ID", "").strip()
        and os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
        and _bucket()
    )


def _bucket() -> str:
    return os.getenv("R2_BUCKET", "").strip()


def _r2_client():
    global _client
    if _client is not None:
        return _client
    import boto3
    from botocore.config import Config

    _client = boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT_URL", "").strip(),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
        region_name=os.getenv("R2_REGION", "auto").strip() or "auto",
        config=Config(signature_version="s3v4"),
    )
    return _client


# 供测试断言列数
assert len(factor_ids()) == 100
