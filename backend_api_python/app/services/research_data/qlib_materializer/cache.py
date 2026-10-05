"""Qlib 派生缓存路径、文件锁、atomic publish、checksum。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.services.research_data import config as rd_config

from .identity import MATERIALIZER_VERSION
from .protocol import MaterializationStatus


def qlib_cache_root(root: Path | None = None) -> Path:
    """Qlib 派生缓存根：{research_cache_dir}/qlib-cache。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / "qlib-cache"
    path.mkdir(parents=True, exist_ok=True)
    (path / "locks").mkdir(parents=True, exist_ok=True)
    return path


def cache_dir_for(materialization_id: str, *, root: Path | None = None) -> Path:
    return qlib_cache_root(root) / materialization_id


def building_dir_for(materialization_id: str, *, root: Path | None = None) -> Path:
    return qlib_cache_root(root) / f"{materialization_id}.building"


def lock_path_for(materialization_id: str, *, root: Path | None = None) -> Path:
    return qlib_cache_root(root) / "locks" / f"{materialization_id}.lock"


def read_manifest(cache_path: Path) -> dict[str, Any] | None:
    """读取 manifest；损坏返回 None。"""
    path = cache_path / "manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_ready_cache(cache_path: Path) -> bool:
    """READY 且 checksum 字段存在则视为可用 hit。"""
    manifest = read_manifest(cache_path)
    if not manifest:
        return False
    if manifest.get("status") != MaterializationStatus.READY.value:
        return False
    if not manifest.get("checksum"):
        return False
    # materializer 版本不匹配视为无效
    if manifest.get("materializer_version") != MATERIALIZER_VERSION:
        return False
    return True


def invalidate(cache_path: Path) -> None:
    """删除派生缓存目录（可重建）。"""
    if cache_path.exists():
        shutil.rmtree(cache_path, ignore_errors=True)


def directory_checksum(cache_path: Path) -> str:
    """对关键产物做逻辑 checksum（路径排序后内容哈希）。"""
    h = hashlib.sha256()
    if not cache_path.exists():
        return h.hexdigest()
    files: list[Path] = []
    for path in cache_path.rglob("*"):
        if not path.is_file():
            continue
        # manifest 本身含 checksum，避免循环：校验时跳过或先算其它文件
        if path.name == "manifest.json":
            continue
        files.append(path)
    for path in sorted(files, key=lambda p: p.relative_to(cache_path).as_posix()):
        rel = path.relative_to(cache_path).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


@contextmanager
def materialization_lock(
    materialization_id: str,
    *,
    root: Path | None = None,
    timeout_sec: float = 120.0,
) -> Iterator[None]:
    """简单文件锁，避免同 id 并发构建。"""
    path = lock_path_for(materialization_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_sec
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            break
        except FileExistsError:
            if time.time() >= deadline:
                raise TimeoutError(f"materialization lock timeout: {materialization_id}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def publish_atomic(building: Path, final: Path) -> None:
    """校验完成后原子发布：先删旧 final，再 rename building → final。"""
    if final.exists():
        shutil.rmtree(final)
    building.rename(final)
