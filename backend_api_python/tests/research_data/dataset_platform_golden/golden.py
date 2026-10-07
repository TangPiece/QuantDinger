"""Phase 9A Dataset Platform golden 环境。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import DatasetDefinition, PricePolicy
from app.services.research_data.data_query import DataQuery
from app.services.research_data.dataset_platform.runner import ResearchDatasetService
from app.services.research_data.registry import LocalJsonRegistry

GOLDEN_DATASET_CODE = "PHASE9A_GOLDEN"
GOLDEN_DATASET_VERSION = "1.0.0"
GOLDEN_DATASET_REF = f"{GOLDEN_DATASET_CODE}@{GOLDEN_DATASET_VERSION}"
GOLDEN_SNAPSHOT_ID = "snap_phase9a_golden"


def golden_snapshot_items() -> list[dict[str, Any]]:
    return [
        {
            "dataset_code": "market_daily",
            "version": "v1",
            "path": "qd/canonical/market/daily/exchange=CN/year=2024/month=01/part-000.parquet",
            "checksum": "sha256:phase9a_market_demo",
            "r2_uri": "r2://quantdinger-data/qd/canonical/market/daily/exchange=CN/year=2024/month=01/part-000.parquet",
        },
        {
            "dataset_code": "universe_CSI300",
            "version": "2024.01",
            "path": "qd/canonical/universe/code=CSI300/version=2024.01/part-000.parquet",
            "checksum": "sha256:phase9a_univ_demo",
        },
    ]


def golden_dataset_definition(*, features: list[str] | None = None) -> DatasetDefinition:
    return DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version=GOLDEN_DATASET_VERSION,
        name="Phase 9A Golden Dataset",
        frequency="1d",
        universe_code="CSI300",
        universe_version="2024.01",
        snapshot_id=GOLDEN_SNAPSHOT_ID,
        schema_version="market_bar_daily@1",
        features=features
        or ["open", "high", "low", "close", "volume", "amount", "vwap"],
        price_policy=PricePolicy(adjustment="none", return_type="price"),
        pit=True,
    )


def golden_bad_pit_inject() -> dict[str, Any]:
    return {"dataset_platform": {"force_pit_false": True}}


def golden_empty_snapshot_inject() -> dict[str, Any]:
    return {"dataset_platform": {"force_empty_snapshot": True}}


def make_dataset_platform_env(
    tmp: Path,
) -> tuple[ResearchDatasetService, LocalJsonRegistry, DataQuery, LocalCanonicalStore]:
    cache = tmp / "cache"
    registry = LocalJsonRegistry(root=tmp / "registry")
    store = LocalCanonicalStore(root=cache / "canonical")
    svc = ResearchDatasetService(cache / "artifacts", registry)
    dq = DataQuery(store, registry)
    return svc, registry, dq, store


__all__ = [
    "GOLDEN_DATASET_CODE",
    "GOLDEN_DATASET_REF",
    "GOLDEN_DATASET_VERSION",
    "GOLDEN_SNAPSHOT_ID",
    "golden_bad_pit_inject",
    "golden_dataset_definition",
    "golden_empty_snapshot_inject",
    "golden_snapshot_items",
    "make_dataset_platform_env",
]
