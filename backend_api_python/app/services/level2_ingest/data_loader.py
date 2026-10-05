"""从 Parquet（本地 staging 或云存储）或本地已解压 CSV 读取三类数据，供策略使用。

`load_one` 的 `source='auto'` 优先级：
本地已解压 CSV → 本地 parquet staging → 云存储（STORAGE_READ 指定 r2|baidu）。
"""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import pyarrow.parquet as pq

from . import config, csv_to_parquet, object_store


def _load_from_cloud(logical_key: str, for_backend: str) -> pd.DataFrame:
    """从指定云后端下载 Parquet 并解析为 DataFrame。"""
    if not object_store.is_read_configured(for_backend):
        raise FileNotFoundError(f"后端 {for_backend} 未配置")
    if not object_store.exists(logical_key, for_backend=for_backend):
        raise FileNotFoundError(logical_key)
    data = object_store.download_bytes(logical_key, for_backend=for_backend)
    return pq.read_table(BytesIO(data)).to_pandas()


def load_one(date: str, code: str, ftype: str, source: str = "auto") -> pd.DataFrame:
    """加载某日某股某类型明细为 DataFrame。

    source:
      - 'auto'  按「本地 CSV → 本地 parquet → STORAGE_READ 云后端」顺序
      - 'csv'   仅本地已解压 CSV
      - 'parquet' 仅本地 parquet staging
      - 'r2'    仅 R2
      - 'baidu' 仅百度网盘
    """
    if source in ("auto", "csv"):
        csv_path = config.local_csv_path(date, code, ftype)
        if csv_path.exists():
            return csv_to_parquet.read_csv_bytes(csv_path.read_bytes(), ftype)

    if source in ("auto", "parquet"):
        pq_path = config.local_parquet_path(date, code, ftype)
        if pq_path.exists():
            return pq.read_table(str(pq_path)).to_pandas()

    logical_key = config.object_key(date, code, ftype)

    if source == "r2":
        return _load_from_cloud(logical_key, "r2")

    if source == "baidu":
        return _load_from_cloud(logical_key, "baidu")

    if source == "auto":
        cloud = object_store.read_backend()
        try:
            return _load_from_cloud(logical_key, cloud)
        except FileNotFoundError:
            pass

    raise FileNotFoundError(f"{date}/{code}/{ftype} 在本地与云存储均未找到")


def load_stock_days(
    code: str,
    dates: list[str],
    ftypes: tuple[str, ...] = config.FILE_TYPES,
    source: str = "auto",
) -> dict[tuple[str, str], pd.DataFrame]:
    """加载某股票多日多类型数据，返回 `{(date, ftype): DataFrame}`。

    缺失的 (date, ftype) 会被跳过（不抛异常），便于容错处理停牌/缺数据。
    """
    data: dict[tuple[str, str], pd.DataFrame] = {}
    for date in dates:
        for ftype in ftypes:
            try:
                data[(date, ftype)] = load_one(date, code, ftype, source=source)
            except FileNotFoundError:
                continue
    return data
