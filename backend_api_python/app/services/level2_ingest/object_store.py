"""统一对象存储门面：按 STORAGE_BACKEND / STORAGE_READ 路由 R2 或百度网盘。"""
from __future__ import annotations

from . import baidu_client, config, r2_client

_BACKENDS = frozenset({"r2", "baidu"})


def _norm(name: str) -> str:
    name = name.strip().lower()
    if name not in _BACKENDS:
        raise ValueError(f"未知存储后端: {name}，可选 r2|baidu")
    return name


def backend() -> str:
    """当前入库后端（STORAGE_BACKEND）。"""
    return _norm(config.STORAGE_BACKEND)


def read_backend() -> str:
    """回测读取优先后端（STORAGE_READ）。"""
    return _norm(config.STORAGE_READ)


def is_configured(for_backend: str | None = None) -> bool:
    """指定或当前入库后端是否已配置凭证。"""
    b = _norm(for_backend) if for_backend else backend()
    if b == "r2":
        return r2_client.is_configured()
    return baidu_client.is_configured()


def is_read_configured(for_backend: str | None = None) -> bool:
    """指定或 STORAGE_READ 后端是否可读。"""
    b = _norm(for_backend) if for_backend else read_backend()
    if b == "r2":
        return r2_client.is_configured()
    return baidu_client.is_configured()


def configure_pool(min_connections: int) -> None:
    """R2 调整连接池；百度为 no-op。"""
    if backend() == "r2":
        r2_client.configure_pool(min_connections)
    else:
        baidu_client.configure_pool(min_connections)


def _client(for_backend: str):
    b = _norm(for_backend)
    if b == "r2":
        return r2_client
    return baidu_client


def _to_remote_key(logical_key: str, for_backend: str) -> str:
    """逻辑键 → 后端原生键/路径。"""
    key = logical_key.lstrip("/")
    if _norm(for_backend) == "r2":
        return key
    return config.baidu_path_from_key(key)


def exists(logical_key: str, for_backend: str | None = None) -> bool:
    b = _norm(for_backend) if for_backend else backend()
    return _client(b).exists(_to_remote_key(logical_key, b))


def list_keys(prefix: str, for_backend: str | None = None) -> list[str]:
    b = _norm(for_backend) if for_backend else backend()
    return _client(b).list_keys(prefix)


def upload_bytes(logical_key: str, data: bytes) -> str:
    """上传到当前 STORAGE_BACKEND，返回 etag/md5。"""
    b = backend()
    return _client(b).upload_bytes(_to_remote_key(logical_key, b), data)


def upload_bytes_for_backend(logical_key: str, data: bytes, for_backend: str) -> str:
    """上传到指定后端（catalog 按 backend 上传时使用）。"""
    b = _norm(for_backend)
    return _client(b).upload_bytes(_to_remote_key(logical_key, b), data)


def download_bytes(logical_key: str, for_backend: str | None = None) -> bytes:
    """从指定或 STORAGE_READ 后端下载。"""
    b = _norm(for_backend) if for_backend else read_backend()
    return _client(b).download_bytes(_to_remote_key(logical_key, b))
