"""CanonicalRepository：DataQuery 唯一对象读入口（Store → 本地落盘 → DuckDB scan）。

硬约束：本模块不得 import CNStockDataSource / market HTTP；只读 CanonicalStore。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import duckdb
import pandas as pd

from . import config
from .canonical_store import CachingCanonicalStore, CanonicalStore, LocalCanonicalStore


class CanonicalRepository:
    """包装 CanonicalStore：物化 parquet 后经 DuckDB `read_parquet` 查询。"""

    def __init__(
        self,
        store: CanonicalStore,
        *,
        materialize_root: Path | None = None,
    ) -> None:
        self._store = store
        # 非 Local 路径时，把对象落到可重复使用的 mirror 目录供 DuckDB 扫描。
        # 惰性创建目录，避免单测仅用 LocalCanonicalStore 时写到 home cache。
        self._materialize_root_arg = materialize_root
        self._materialize_root: Path | None = (
            Path(materialize_root) if materialize_root is not None else None
        )

    @property
    def store(self) -> CanonicalStore:
        return self._store

    def list_keys(self, prefix: str) -> list[str]:
        return self._store.list_keys(prefix)

    def exists(self, key: str) -> bool:
        return self._store.exists(key)

    def cache_stats(self) -> dict[str, int] | None:
        """若底层为 CachingCanonicalStore 则返回 hit/miss，否则 None。"""
        if isinstance(self._store, CachingCanonicalStore):
            return self._store.stats()
        return None

    def _ensure_materialize_root(self) -> Path:
        """返回并确保 materialize 根目录存在。"""
        if self._materialize_root is None:
            self._materialize_root = config.research_cache_dir() / "duckdb_materialize"
        self._materialize_root.mkdir(parents=True, exist_ok=True)
        return self._materialize_root

    def materialize_path(self, key: str) -> Path:
        """确保对象在本地文件系统，返回绝对路径（供 DuckDB 使用）。"""
        # LocalCanonicalStore：直接用根目录文件，避免二次拷贝
        if isinstance(self._store, LocalCanonicalStore):
            path = self._store._path(key)
            if not path.is_file():
                raise FileNotFoundError(key)
            return path

        # CachingCanonicalStore：先 get 触发 miss→mirror，再读 local 路径
        if isinstance(self._store, CachingCanonicalStore):
            if not self._store.local.exists(key):
                self._store.get_bytes(key)  # miss + 回填；计入 misses
            else:
                # 已在 local：计一次 hit（与 get_bytes 语义一致，便于 cache 测试）
                self._store.hits += 1
            return self._store.local._path(key)

        # 其它 Store：落到 materialize_root
        root = self._ensure_materialize_root()
        dest = root / key.lstrip("/")
        if not dest.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self._store.get_bytes(key))
        return dest

    def read_parquet_df(
        self,
        keys: Sequence[str] | None = None,
        *,
        prefix: str | None = None,
        order_by: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """用 DuckDB 读取一个或多个 parquet 键；列序/类型由引擎稳定化。

        Args:
            keys: 显式对象键列表；与 prefix 二选一（可同时，取并集）。
            prefix: 列出该前缀下全部 `.parquet`。
            order_by: 可选排序列，保证跨次查询行序稳定。
        """
        resolved: list[str] = []
        if keys:
            resolved.extend(list(keys))
        if prefix is not None:
            for key in self._store.list_keys(prefix):
                if key.endswith(".parquet"):
                    resolved.append(key)
        # 去重保序
        seen: set[str] = set()
        uniq: list[str] = []
        for key in resolved:
            if key not in seen and key.endswith(".parquet"):
                seen.add(key)
                uniq.append(key)
        if not uniq:
            return pd.DataFrame()

        paths = [str(self.materialize_path(k)) for k in uniq]
        con = duckdb.connect(database=":memory:")
        try:
            # 单文件传 str，多文件传 list；DuckDB 参数绑定避免路径注入
            param: str | list[str] = paths[0] if len(paths) == 1 else paths
            sql = "SELECT * FROM read_parquet(?)"
            if order_by:
                cols = ", ".join(f'"{c}"' for c in order_by)
                sql = f"{sql} ORDER BY {cols}"
            return con.execute(sql, [param]).fetchdf()
        finally:
            con.close()
