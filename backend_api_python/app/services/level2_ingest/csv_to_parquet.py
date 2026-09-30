"""CSV → Parquet 忠实转换。

支持文件与字节两种输入：本地 CSV 转 Parquet，或内存字节供上传路径使用。
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import schema


def read_csv_bytes(csv_bytes: bytes, ftype: str) -> pd.DataFrame:
    """将 gb18030 编码的 CSV 字节读入并规范化。

    全列先按字符串读入（`dtype=str` + `keep_default_na=False` 保留空字段原文），
    再交给 `schema.normalize` 做时间补零、去空列、数值列定型，忠实保留所有行。
    """
    df = pd.read_csv(
        BytesIO(csv_bytes),
        encoding="gb18030",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    return schema.normalize(df, ftype)


def dataframe_to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """DataFrame → parquet 字节（zstd 压缩）。"""
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


def csv_bytes_to_parquet_bytes(csv_bytes: bytes, ftype: str) -> bytes:
    """CSV 字节 → parquet 字节（内存流式转换，供 pipeline 直接上传 R2）。"""
    df = read_csv_bytes(csv_bytes, ftype)
    return dataframe_to_parquet_bytes(df)


def csv_file_to_parquet(csv_path: str | Path, parquet_path: str | Path, ftype: str) -> Path:
    """本地 CSV 文件 → 本地 parquet 文件（用于已解压数据的离线转换）。"""
    csv_path = Path(csv_path)
    parquet_path = Path(parquet_path)
    df = read_csv_bytes(csv_path.read_bytes(), ftype)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, str(parquet_path), compression="zstd")
    return parquet_path
