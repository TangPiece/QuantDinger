"""研究数据层环境配置（与 Level2 D1_WORKER_* 隔离）。"""

from __future__ import annotations

import os
from pathlib import Path


def canonical_prefix() -> str:
    """R2/本地研究根前缀，默认 qd。"""
    return (os.getenv("QD_CANONICAL_PREFIX") or "qd").strip().strip("/") or "qd"


def research_cache_dir() -> Path:
    """本地热缓存根目录。"""
    raw = (os.getenv("QD_RESEARCH_CACHE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".quantdinger" / "cache"


def d1_research_worker_url() -> str:
    return os.getenv("D1_RESEARCH_WORKER_URL", "").strip()


def d1_research_worker_token() -> str:
    return os.getenv("D1_RESEARCH_WORKER_TOKEN", "").strip()


def d1_research_configured() -> bool:
    return bool(d1_research_worker_url() and d1_research_worker_token())
