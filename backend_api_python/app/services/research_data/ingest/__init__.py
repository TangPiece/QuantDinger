"""Source → Canonical 入库（仅 ingest 脚本使用；DataQuery 禁止依赖本包）。"""

from .build_golden import build_golden_dataset

__all__ = ["build_golden_dataset"]
