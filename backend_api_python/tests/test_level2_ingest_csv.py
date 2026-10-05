"""用内存里的一小段 CSV 确认转成 Parquet 后列还在，不读真实归档。"""
from io import BytesIO

import pyarrow.parquet as pq

from app.services.level2_ingest.csv_to_parquet import csv_bytes_to_parquet_bytes, read_csv_bytes


def test_trade_csv_roundtrip_keeps_columns() -> None:
    raw = "成交代码,时间,成交价格,成交数量,BS标志,叫买序号,叫卖序号,\n0,93000000,100000,100,B,1,2,\n".encode("gb18030")
    expected = read_csv_bytes(raw, "逐笔成交")
    actual = pq.read_table(BytesIO(csv_bytes_to_parquet_bytes(raw, "逐笔成交"))).to_pandas()
    assert actual["时间"].tolist() == expected["时间"].tolist()
    assert actual["时间"].iloc[0] == "093000000"
    assert actual["成交价格"].iloc[0] == 100000
