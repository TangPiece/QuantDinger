"""MiningRun / Candidate 引用与 R2 键。"""

from __future__ import annotations

import uuid

from app.services.research_data import config as rd_config


def new_mining_run_id() -> str:
    return f"mrun_{uuid.uuid4().hex[:16]}"


def new_candidate_id() -> str:
    return f"mcand_{uuid.uuid4().hex[:16]}"


def mining_run_index_key(*, mining_run_hash: str) -> str:
    h = str(mining_run_hash or "")[:32]
    root = rd_config.canonical_prefix()
    return f"{root}/mining_platform/run/{h}/run_index.json"


def candidate_key(*, mining_run_id: str, candidate_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/mining_platform/run/{mining_run_id}/candidates/{candidate_id}.json"


def mining_score_key(*, mining_run_id: str, candidate_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/mining_platform/run/{mining_run_id}/scores/{candidate_id}.json"


def list_runs_prefix() -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/mining_platform/run/"


__all__ = [
    "candidate_key",
    "list_runs_prefix",
    "mining_run_index_key",
    "mining_score_key",
    "new_candidate_id",
    "new_mining_run_id",
]
