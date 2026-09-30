"""入库 catalog：按后端（r2/baidu）分文件，批量判断已上传对象。"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from . import config, object_store

_CATALOG_COLS = ["date", "code", "ftype", "r2_key", "rows", "bytes", "etag", "uploaded_at", "backend"]
_BACKENDS = frozenset({"r2", "baidu"})


def _resolve_backend(backend: str | None) -> str:
    b = (backend or object_store.backend()).strip().lower()
    if b not in _BACKENDS:
        raise ValueError(f"未知 catalog 后端: {b}")
    return b


def _empty_catalog() -> pd.DataFrame:
    return pd.DataFrame(columns=_CATALOG_COLS)


def _legacy_catalog_path(date: str) -> Path:
    """旧版单文件 catalog 路径（迁移用）。"""
    return config.CATALOG_DIR / f"{date}.parquet"


def migrate_legacy_catalogs() -> list[str]:
    """将 .staging/catalogs/{date}.parquet 迁入 catalogs/r2/（20260803 部分进度不迁移）。"""
    moved: list[str] = []
    legacy_dir = config.CATALOG_DIR
    r2_dir = legacy_dir / "r2"
    r2_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "baidu").mkdir(parents=True, exist_ok=True)

    for path in sorted(legacy_dir.glob("*.parquet")):
        date = path.stem
        # 旧 R2 部分进度 catalog 丢弃，全量手动上传后 sync 重建
        if date == "20260803":
            path.unlink(missing_ok=True)
            continue
        dest = r2_dir / path.name
        if dest.exists():
            path.unlink(missing_ok=True)
            continue
        shutil.move(str(path), str(dest))
        moved.append(date)
    return moved


def load_catalog(date: str, backend: str | None = None) -> pd.DataFrame:
    """加载指定后端的 catalog：本地 → 远程 → 空表。"""
    b = _resolve_backend(backend)
    local_path = config.local_catalog_path(date, backend=b)
    if local_path.exists():
        df = pq.read_table(str(local_path)).to_pandas()
        if "backend" not in df.columns:
            df["backend"] = b
        return df

    remote_key = config.catalog_object_key(date, backend=b)
    try:
        if object_store.is_configured(b) and object_store.exists(remote_key, for_backend=b):
            df = pq.read_table(
                BytesIO(object_store.download_bytes(remote_key, for_backend=b))
            ).to_pandas()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if "backend" not in df.columns:
                df["backend"] = b
            df.to_parquet(local_path, index=False)
            return df
    except Exception:
        pass
    return _empty_catalog()


def get_uploaded_keys(date: str, backend: str | None = None) -> set[str]:
    """返回该日、该后端已入库的对象逻辑键集合。"""
    df = load_catalog(date, backend=backend)
    if df.empty:
        return set()
    return set(df["r2_key"].astype(str))


# 待落盘缓冲：backend:date -> rows
_pending: dict[str, list[dict]] = {}


def _pending_key(date: str, backend: str) -> str:
    return f"{backend}:{date}"


def record_upload(
    date: str,
    code: str,
    ftype: str,
    rows: int,
    nbytes: int,
    etag: str = "",
) -> None:
    """追加上传记录到当前 STORAGE_BACKEND 的内存缓冲。"""
    b = object_store.backend()
    key = config.object_key(date, code, ftype)
    _pending.setdefault(_pending_key(date, b), []).append({
        "date": date,
        "code": code,
        "ftype": ftype,
        "r2_key": key,
        "rows": rows,
        "bytes": nbytes,
        "etag": etag,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "backend": b,
    })


def flush_catalog(date: str, backend: str | None = None) -> None:
    """将内存缓冲合并写入对应后端的本地 catalog。"""
    b = _resolve_backend(backend)
    pk = _pending_key(date, b)
    rows = _pending.pop(pk, [])
    if not rows:
        return
    local_path = config.local_catalog_path(date, backend=b)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    df = load_catalog(date, backend=b)
    new_df = pd.DataFrame(rows)
    df = pd.concat(
        [df[~df["r2_key"].isin(new_df["r2_key"])], new_df],
        ignore_index=True,
    )
    df.to_parquet(local_path, index=False)


def sync_from_remote_prefix(date: str, backend: str | None = None) -> set[str]:
    """从指定后端列举 prefix，重写该后端的本地 catalog（不碰另一后端）。"""
    b = _resolve_backend(backend)
    prefix = f"{config.R2_PREFIX}/{date}/"
    keys = object_store.list_keys(prefix, for_backend=b)
    if not keys:
        return set()

    rows = []
    for key in keys:
        if not key.endswith(".parquet"):
            continue
        parts = key.split("/")
        if len(parts) < 4:
            continue
        code, fname = parts[-2], parts[-1]
        ftype = fname.replace(".parquet", "")
        rows.append({
            "date": date,
            "code": code,
            "ftype": ftype,
            "r2_key": key,
            "rows": 0,
            "bytes": 0,
            "etag": "",
            "uploaded_at": "",
            "backend": b,
        })
    if rows:
        local_path = config.local_catalog_path(date, backend=b)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(local_path, index=False)
    return set(keys)


def sync_from_r2_prefix(date: str) -> set[str]:
    """兼容旧名：仅同步 R2 catalog。"""
    return sync_from_remote_prefix(date, backend="r2")


def upload_catalog(date: str, backend: str | None = None) -> None:
    """将指定后端的本地 catalog 上传到对应远程路径。"""
    b = _resolve_backend(backend)
    path = config.local_catalog_path(date, backend=b)
    if not path.exists():
        return
    object_store.upload_bytes_for_backend(
        config.catalog_object_key(date, backend=b),
        path.read_bytes(),
        for_backend=b,
    )
