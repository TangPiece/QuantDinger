"""Phase 8B：candidate_id 构造（与 8A strategy_code 规范对齐）。"""

from __future__ import annotations

import re

from app.services.strategy_registry.identity import (
    InvalidStrategyIdentityError,
    normalize_strategy_code,
)

_CAND_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


class InvalidCandidateIdentityError(ValueError):
    """非法 candidate_version / candidate_id。"""


def normalize_candidate_version(raw: str) -> str:
    """候选版本 label（独立于 8A strategy_version）。"""
    text = str(raw or "").strip().lower()
    text = re.sub(r"[\s]+", "_", text)
    if not text or not _CAND_VERSION_RE.match(text):
        raise InvalidCandidateIdentityError(
            f"invalid candidate_version: {raw!r}; expect ^[a-z0-9][a-z0-9._-]{{0,62}}$"
        )
    return text


def build_candidate_id(
    strategy_code: str,
    candidate_version: str,
    content_hash: str,
) -> str:
    """确定性 candidate_id；同 evidence 幂等。"""
    code = normalize_strategy_code(strategy_code)
    ver = normalize_candidate_version(candidate_version)
    pin = str(content_hash or "").strip()
    if len(pin) < 8:
        raise InvalidCandidateIdentityError("content_hash too short for candidate_id")
    safe_pin = pin[:8]
    return f"{code}@{ver}@{safe_pin}"


__all__ = [
    "InvalidCandidateIdentityError",
    "InvalidStrategyIdentityError",
    "build_candidate_id",
    "normalize_candidate_version",
    "normalize_strategy_code",
]
