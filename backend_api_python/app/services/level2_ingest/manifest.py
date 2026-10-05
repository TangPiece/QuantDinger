"""7z 归档 manifest：避免每次 tar -tf 列目录（solid 7z 极慢）。"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from . import config, extract, object_store


@dataclass
class Member:
    date: str
    code: str
    ftype: str
    archive_path: str
    member_path: str
    size_bytes: int | None = None


def _df_to_members(df: pd.DataFrame) -> list[Member]:
    out: list[Member] = []
    for row in df.itertuples(index=False):
        out.append(Member(
            date=row.date, code=row.code, ftype=row.ftype,
            archive_path=row.archive_path, member_path=row.member_path,
            size_bytes=getattr(row, "size_bytes", None),
        ))
    return out


def _members_to_df(members: list[Member], archive_path: str) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": m.date, "code": m.code, "ftype": m.ftype,
            "archive_path": archive_path, "member_path": m.member_path,
            "size_bytes": m.size_bytes,
        }
        for m in members
    ])


def build_from_archive(seven_z_path: str | Path) -> list[Member]:
    """一次性扫描 .7z 生成 manifest（仅 build_manifest 调用）。"""
    seven_z_path = Path(seven_z_path)
    members: list[Member] = []
    archive_date = seven_z_path.stem
    for member_path in extract.list_members(seven_z_path):
        # 归档可能是 {code}/{ftype}.csv（无日期层），用文件名 stem 补日期
        date, code, ftype = extract.parse_member(
            member_path, archive_date=archive_date
        )
        members.append(Member(
            date=date, code=code, ftype=ftype,
            archive_path=str(seven_z_path), member_path=member_path,
        ))
    return members


def save_local(date: str, members: list[Member], archive_path: str) -> Path:
    """写入本地 .staging/manifests/{date}.parquet。"""
    config.MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = config.local_manifest_path(date)
    df = _members_to_df(members, archive_path)
    df.to_parquet(path, index=False)
    return path


def upload_to_r2(date: str, members: list[Member], archive_path: str) -> None:
    """上传 manifest 到当前入库后端（兼容旧函数名）。"""
    buf = BytesIO()
    _members_to_df(members, archive_path).to_parquet(buf, index=False)
    object_store.upload_bytes(config.manifest_object_key(date), buf.getvalue())


def load_manifest(date: str, seven_z_path: str | Path | None = None) -> list[Member]:
    """加载 manifest：本地 parquet → R2 → 回退 tar -tf（并缓存到本地）。

    正常 pipeline 应只走前两级，禁止反复 list_members。
    """
    local_path = config.local_manifest_path(date)
    if local_path.exists():
        df = pq.read_table(str(local_path)).to_pandas()
        return _df_to_members(df)

    remote_key = config.manifest_object_key(date)
    try:
        if object_store.is_configured() and object_store.exists(remote_key):
            df = pq.read_table(
                BytesIO(object_store.download_bytes(remote_key))
            ).to_pandas()
            config.MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
            df.to_parquet(local_path, index=False)
            return _df_to_members(df)
    except Exception:
        pass

    if seven_z_path is None:
        seven_z_path = config.DATA_ROOT / f"{date}.7z"
    seven_z_path = Path(seven_z_path)
    if not seven_z_path.exists():
        raise FileNotFoundError(f"无 manifest 且找不到归档: {seven_z_path}")

    members = build_from_archive(seven_z_path)
    save_local(date, members, str(seven_z_path))
    return members
