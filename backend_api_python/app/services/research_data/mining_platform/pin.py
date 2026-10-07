"""钉住 Dataset + FeatureUniverse + Policy → MiningRun 索引。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.research_data.contracts import DatasetHandle

from .hashing import compute_mining_run_hash
from .identity import mining_run_index_key, new_mining_run_id
from .protocol import (
    ENGINE_VERSION,
    MINING_RUN_INDEX_SCHEMA,
    FactorCandidate,
    MiningRun,
    MiningRunIndex,
    MiningRunStatus,
    SELECTION_BIAS_WARNING,
)


def pin_mining_run(
    *,
    dataset_ref: str,
    handle: DatasetHandle,
    feature_set_hash: str,
    mining_policy_id: str,
    mining_policy_content_hash: str,
    evaluation_policy_id: str,
    evaluation_policy_version: str,
    random_seed: int,
    status: MiningRunStatus,
    total_candidates_generated: int = 0,
    total_candidates_screened: int = 0,
    total_candidates_tested: int = 0,
    total_survivors: int = 0,
    candidates: list[FactorCandidate] | None = None,
    mining_run_id: str | None = None,
    published_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[MiningRunIndex, MiningRun]:
    ts = published_at or datetime.now(timezone.utc)
    run_hash = compute_mining_run_hash(
        dataset_hash=handle.dataset_hash,
        feature_set_hash=feature_set_hash,
        mining_policy_content_hash=mining_policy_content_hash,
        evaluation_policy_version=evaluation_policy_version,
        random_seed=random_seed,
    )
    rid = mining_run_id or new_mining_run_id()
    cands = list(candidates or [])
    bias = SELECTION_BIAS_WARNING if total_candidates_tested > 1 else ""
    idx = MiningRunIndex(
        schema_version=MINING_RUN_INDEX_SCHEMA,
        engine_version=ENGINE_VERSION,
        mining_run_id=rid,
        mining_run_hash=run_hash,
        status=status,
        dataset_ref=dataset_ref,
        dataset_hash=handle.dataset_hash,
        feature_set_hash=feature_set_hash,
        mining_policy_id=mining_policy_id,
        mining_policy_content_hash=mining_policy_content_hash,
        evaluation_policy_id=evaluation_policy_id,
        evaluation_policy_version=evaluation_policy_version,
        random_seed=random_seed,
        total_candidates_generated=total_candidates_generated,
        total_candidates_screened=total_candidates_screened,
        total_candidates_tested=total_candidates_tested,
        total_survivors=total_survivors,
        selection_bias_warning=bias,
        candidate_ids=[c.candidate_id for c in cands],
        immutable=True,
        published_at=ts,
        metadata={
            "r2_key": mining_run_index_key(mining_run_hash=run_hash),
            **(metadata or {}),
        },
    )
    run = MiningRun(
        mining_run_id=rid,
        mining_run_hash=run_hash,
        status=status,
        dataset_ref=dataset_ref,
        dataset_hash=handle.dataset_hash,
        feature_set_hash=feature_set_hash,
        mining_policy_id=mining_policy_id,
        mining_policy_content_hash=mining_policy_content_hash,
        evaluation_policy_id=evaluation_policy_id,
        evaluation_policy_version=evaluation_policy_version,
        random_seed=random_seed,
        total_candidates_generated=total_candidates_generated,
        total_candidates_screened=total_candidates_screened,
        total_candidates_tested=total_candidates_tested,
        total_survivors=total_survivors,
        selection_bias_warning=bias,
        candidates=cands,
        published_at=ts,
        metadata=dict(idx.metadata),
    )
    return idx, run


__all__ = ["pin_mining_run"]
