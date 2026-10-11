"""Level2 批量入库：解压、CSV 转 Parquet、上传百度网盘或 R2。

百因子批量闭环用 scripts/run_level2_l2_daily.sh（解压后 CSV 直算）。
旧热表补数用 scripts/run_level2_factors.sh（读已有 staging Parquet）。
不进 API 进程。
"""
