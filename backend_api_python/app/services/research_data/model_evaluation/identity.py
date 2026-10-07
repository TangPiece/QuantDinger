"""Model Evaluation 身份与路径键。"""

from __future__ import annotations

import uuid

from app.services.research_data import config as rd_config


def new_evaluation_run_id() -> str:
    return f"mevr_{uuid.uuid4().hex[:16]}"


def evaluation_run_key(*, evaluation_run_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/model_evaluation/runs/{evaluation_run_id}.json"


def evaluation_bundle_prefix(*, evaluation_run_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/artifacts/evaluation/{evaluation_run_id}"


__all__ = [
    "evaluation_bundle_prefix",
    "evaluation_run_key",
    "new_evaluation_run_id",
]
