"""Canonical 对象存储抽象：Local / R2（委托 level2_ingest.r2_client）。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from . import config


class CanonicalStore(Protocol):
    """研究事实数据读写面；键为相对 qd/ 的逻辑对象键。"""

    def put_bytes(self, key: str, data: bytes) -> str:
        """写入并返回 checksum 或 etag。"""

    def get_bytes(self, key: str) -> bytes:
        ...

    def exists(self, key: str) -> bool:
        ...

    def list_keys(self, prefix: str) -> list[str]:
        ...


class LocalCanonicalStore:
    """本地目录实现，供单测与离线开发。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or config.research_cache_dir() / "canonical_root")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        rel = key.lstrip("/")
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put_bytes(self, key: str, data: bytes) -> str:
        import hashlib

        path = self._path(key)
        path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list_keys(self, prefix: str) -> list[str]:
        pref = prefix.lstrip("/")
        base = self.root / pref if pref else self.root
        if not base.exists():
            # prefix 可能是文件前缀而非目录
            parent = self.root
            keys: list[str] = []
            for path in parent.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(self.root).as_posix()
                if rel.startswith(pref):
                    keys.append(rel)
            return sorted(keys)
        if base.is_file():
            return [pref]
        keys = []
        for path in base.rglob("*"):
            if path.is_file():
                keys.append(path.relative_to(self.root).as_posix())
        return sorted(keys)


class R2CanonicalStore:
    """委托现有 level2_ingest.r2_client；不修改 ingest 源码。"""

    def put_bytes(self, key: str, data: bytes) -> str:
        from app.services.level2_ingest import r2_client

        return r2_client.upload_bytes(key, data)

    def get_bytes(self, key: str) -> bytes:
        from app.services.level2_ingest import r2_client

        return r2_client.download_bytes(key)

    def exists(self, key: str) -> bool:
        from app.services.level2_ingest import r2_client

        return r2_client.exists(key)

    def list_keys(self, prefix: str) -> list[str]:
        from app.services.level2_ingest import r2_client

        return r2_client.list_keys(prefix)


class CachingCanonicalStore:
    """读 R2 时回填本地 mirror。"""

    def __init__(self, remote: CanonicalStore, local: LocalCanonicalStore) -> None:
        self.remote = remote
        self.local = local

    def put_bytes(self, key: str, data: bytes) -> str:
        checksum = self.remote.put_bytes(key, data)
        self.local.put_bytes(key, data)
        return checksum

    def get_bytes(self, key: str) -> bytes:
        if self.local.exists(key):
            return self.local.get_bytes(key)
        data = self.remote.get_bytes(key)
        self.local.put_bytes(key, data)
        return data

    def exists(self, key: str) -> bool:
        return self.local.exists(key) or self.remote.exists(key)

    def list_keys(self, prefix: str) -> list[str]:
        remote_keys = self.remote.list_keys(prefix)
        if remote_keys:
            return remote_keys
        return self.local.list_keys(prefix)
