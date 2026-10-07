"""Phase 9B Feature / Factor Platform golden 环境。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import FeatureDefinition, PricePolicy
from app.services.research_data.data_query import DataQuery
from app.services.research_data.dataset_platform.runner import ResearchDatasetService
from app.services.research_data.feature_factor_platform.feature_set import FeatureSetDefinition
from app.services.research_data.feature_factor_platform.pipeline import FactorPipelineSpec
from app.services.research_data.feature_factor_platform.runner import FeatureFactorService
from app.services.research_data.factor_lab import FactorComputeService
from app.services.research_data.factor_lab.artifact_store import FactorDatasetArtifactStore
from app.services.research_data.registry import LocalJsonRegistry
from dataset_platform_golden.golden import (
    GOLDEN_DATASET_REF,
    golden_dataset_definition,
    golden_snapshot_items,
    make_dataset_platform_env,
)
from factor_lab_compute.golden import INSTRUMENTS, seed_market, seed_pit_fundamental

GOLDEN_FEATURE_CODE = "PHASE9B_RAW_CLOSE"
GOLDEN_FEATURE_VERSION = "1.0.0"
GOLDEN_FEATURE_REF = f"{GOLDEN_FEATURE_CODE}@{GOLDEN_FEATURE_VERSION}"

GOLDEN_FACTOR_CODE = "PHASE9B_MOMENTUM"
GOLDEN_FACTOR_VERSION = "1.0.0"
GOLDEN_FACTOR_REF = f"{GOLDEN_FACTOR_CODE}@{GOLDEN_FACTOR_VERSION}"

GOLDEN_FS_CODE = "PHASE9B_FS"
GOLDEN_FS_VERSION = "1.0.0"
GOLDEN_FS_REF = f"{GOLDEN_FS_CODE}@{GOLDEN_FS_VERSION}"


def golden_feature_definition() -> FeatureDefinition:
    return FeatureDefinition(
        code=GOLDEN_FEATURE_CODE,
        version=GOLDEN_FEATURE_VERSION,
        name="Golden raw close proxy",
        expression="close",
        factor_type="TECHNICAL",
        computation_engine="quantdinger",
        dependencies=["market:CNStock"],
        information_policy="NON_PIT",
        price_policy=PricePolicy(adjustment="none"),
    )


def golden_factor_definition(*, pipeline: bool = True) -> FeatureDefinition:
    sidecar: dict[str, Any] = {}
    if pipeline:
        sidecar["factor_pipeline"] = FactorPipelineSpec(
            winsorize={"method": "mad", "n": 3},
            normalize={"method": "zscore"},
            direction="long",
        ).model_dump(mode="json")
    return FeatureDefinition(
        code=GOLDEN_FACTOR_CODE,
        version=GOLDEN_FACTOR_VERSION,
        name="Golden momentum factor",
        expression="momentum_20",
        factor_type="TECHNICAL",
        computation_engine="quantdinger",
        dependencies=["market:CNStock"],
        information_policy="NON_PIT",
        price_policy=PricePolicy(adjustment="none"),
        definition=sidecar,
    )


def golden_feature_set_definition(
    *, members: list[str] | None = None
) -> FeatureSetDefinition:
    return FeatureSetDefinition(
        code=GOLDEN_FS_CODE,
        version=GOLDEN_FS_VERSION,
        name="Phase 9B golden feature set",
        member_refs=members or [GOLDEN_FACTOR_REF],
        processor="identity",
        schema_version="feature_set@1",
    )


def make_feature_factor_env(
    tmp: Path,
) -> tuple[
    FeatureFactorService,
    ResearchDatasetService,
    LocalJsonRegistry,
    DataQuery,
    FactorComputeService,
    list[Any],
]:
    """9A dataset + 4B compute + 9B platform（单 registry / cache 根）。"""
    base = tmp / "env"
    ds_svc, registry, _dq_ds, _canon_ds = make_dataset_platform_env(base / "dataset")
    ds_svc.build_and_register(
        golden_dataset_definition(), snapshot_items=golden_snapshot_items()
    )
    store = LocalCanonicalStore(root=base / "canonical")
    days = seed_market(store, registry)
    seed_pit_fundamental(store, registry)
    query = DataQuery(store, registry)
    compute = FactorComputeService(
        query,
        registry,
        store,
        artifact_store=FactorDatasetArtifactStore(root=base / "factor_art"),
    )
    ff = FeatureFactorService(
        base / "ff_art",
        registry,
        query=query,
        dataset_svc=ds_svc,
        compute=compute,
    )
    return ff, ds_svc, registry, query, compute, days


def build_window(days) -> tuple[str, str]:
    return days[0].isoformat(), days[-1].isoformat()


def compute_metadata_inject() -> dict[str, Any]:
    return {
        "feature_factor_platform": {
            "compute_metadata": {"instruments": INSTRUMENTS, "exchange": "CN"},
        }
    }


__all__ = [
    "GOLDEN_DATASET_REF",
    "GOLDEN_FACTOR_REF",
    "GOLDEN_FEATURE_REF",
    "GOLDEN_FS_REF",
    "build_window",
    "compute_metadata_inject",
    "golden_factor_definition",
    "golden_feature_definition",
    "golden_feature_set_definition",
    "make_feature_factor_env",
]
