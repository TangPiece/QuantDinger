"""Phase 9E Factor Library golden 环境。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.factor_library_platform.protocol import FactorLibraryInject
from app.services.research_data.factor_library_platform.runner import FactorLibraryService
from evaluation_platform_golden.golden import (
    GOLDEN_DATASET_REF,
    GOLDEN_FACTOR_REF,
    GOLDEN_POLICY_ID,
    evaluation_inject,
    make_evaluation_platform_env,
)

GOLDEN_FACTOR_REF_B = "golden_stub_factor_b@1.0.0"


def library_inject(**kwargs: Any) -> dict[str, Any]:
    section: dict[str, Any] = {
        "auto_activate": False,
        "gate_config": {"min_quality_total": 0.0},
        "cluster_corr_matrix": {},
        "weight_metrics": {},
    }
    section.update(kwargs)
    return {"factor_library_platform": section}


def make_factor_library_env(
    tmp: Path,
) -> tuple[FactorLibraryService, Any, Any, Any, list[Any], tuple[str, str]]:
    eval_svc, ds_svc, registry, days, window = make_evaluation_platform_env(tmp / "stack")
    ff = eval_svc._factor_svc  # type: ignore[attr-defined]
    lib = FactorLibraryService(
        tmp / "library_art",
        registry,
        factor_svc=ff,
        eval_svc=eval_svc,
    )
    return lib, eval_svc, ds_svc, registry, days, window


def run_golden_evaluation(eval_svc: Any, window: tuple[str, str], days: list[Any]) -> Any:
    return eval_svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        policy_id=GOLDEN_POLICY_ID,
        window=window,
        inject=evaluation_inject(days=days),
    )


__all__ = [
    "GOLDEN_FACTOR_REF",
    "GOLDEN_FACTOR_REF_B",
    "FactorLibraryInject",
    "library_inject",
    "make_factor_library_env",
    "run_golden_evaluation",
]
