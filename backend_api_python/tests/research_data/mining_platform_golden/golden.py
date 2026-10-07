"""Phase 9D Mining Platform golden 环境。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.mining_platform.protocol import MiningJob
from app.services.research_data.mining_platform.runner import FactorMiningService
from evaluation_platform_golden.golden import (
    GOLDEN_DATASET_REF,
    GOLDEN_POLICY_ID,
    make_evaluation_platform_env,
    register_golden_policies,
)

GOLDEN_MINING_POLICY_ID = "phase9d_golden_v1"
GOLDEN_RANDOM_SEED = 42


def mining_inject(*, skip_build_eval: bool = True, **kwargs: Any) -> dict[str, Any]:
    section: dict[str, Any] = {
        "skip_build_eval": skip_build_eval,
        "fast_screen_pass_all": False,
        "screen_ic_threshold": 0.0,
        "synthetic_evaluation_scores": {},
    }
    section.update(kwargs)
    return {"mining_platform": section}


def golden_mining_job(*, holdout: bool = True) -> MiningJob:
    return MiningJob(
        dataset_ref=GOLDEN_DATASET_REF,
        feature_columns=["close", "open", "high", "low"],
        mining_policy_id=GOLDEN_MINING_POLICY_ID,
        evaluation_policy_id=GOLDEN_POLICY_ID,
        random_seed=GOLDEN_RANDOM_SEED,
        train_start="2020-01-02",
        train_end="2020-01-20",
        holdout_start="2020-01-21" if holdout else "",
        holdout_end="2020-01-28" if holdout else "",
    )


def make_mining_platform_env(
    tmp: Path,
) -> tuple[FactorMiningService, Any, Any, MiningJob]:
    register_golden_policies()
    eval_svc, ds_svc, registry, _days, _window = make_evaluation_platform_env(tmp / "stack")
    from app.services.research_data.feature_factor_platform.runner import FeatureFactorService

    ff = eval_svc._factor_svc  # type: ignore[attr-defined]
    assert isinstance(ff, FeatureFactorService)
    mining = FactorMiningService(
        tmp / "mining_art",
        registry,
        factor_svc=ff,
        eval_svc=eval_svc,
        dataset_svc=ds_svc,
    )
    job = golden_mining_job()
    return mining, ds_svc, registry, job


__all__ = [
    "GOLDEN_MINING_POLICY_ID",
    "GOLDEN_RANDOM_SEED",
    "golden_mining_job",
    "make_mining_platform_env",
    "mining_inject",
]
