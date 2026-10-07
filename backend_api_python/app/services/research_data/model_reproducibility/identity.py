"""Reproducibility 身份与路径键。"""

from __future__ import annotations

import uuid

from app.services.research_data import config as rd_config


def new_repro_manifest_id() -> str:
    return f"rprm_{uuid.uuid4().hex[:16]}"


def new_reproducibility_run_id() -> str:
    return f"rprr_{uuid.uuid4().hex[:16]}"


def repro_manifest_key(*, repro_manifest_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/model_reproducibility/manifests/{repro_manifest_id}.json"


def reproducibility_run_key(*, reproducibility_run_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/model_reproducibility/runs/{reproducibility_run_id}.json"


def reproducibility_bundle_prefix(*, reproducibility_run_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/artifacts/reproducibility/{reproducibility_run_id}"


__all__ = [
    "new_repro_manifest_id",
    "new_reproducibility_run_id",
    "repro_manifest_key",
    "reproducibility_bundle_prefix",
    "reproducibility_run_key",
]
