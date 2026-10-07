"""EvaluationRun 引用与 R2 键。"""

from __future__ import annotations

import uuid

from app.services.research_data import config as rd_config


def split_ref(ref: str) -> tuple[str, str]:
    text = str(ref or "").strip()
    if "@" not in text:
        raise ValueError(f"invalid ref: {ref!r}")
    code, version = text.split("@", 1)
    if not code or not version:
        raise ValueError(f"invalid ref: {ref!r}")
    return code, version


def new_evaluation_id() -> str:
    return f"evrun_{uuid.uuid4().hex[:16]}"


def evaluation_run_index_key(*, run_content_hash: str) -> str:
    """按 content hash 槽位存储（幂等键）。"""
    h = str(run_content_hash or "")[:32]
    root = rd_config.canonical_prefix()
    return f"{root}/evaluation_platform/run/{h}/run_index.json"


def quality_score_key(*, evaluation_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/evaluation_platform/score/{evaluation_id}/quality_score.json"


def list_runs_prefix() -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/evaluation_platform/run/"


__all__ = [
    "evaluation_run_index_key",
    "list_runs_prefix",
    "new_evaluation_id",
    "quality_score_key",
    "split_ref",
]
