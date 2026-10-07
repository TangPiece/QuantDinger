"""Phase 8A Golden：Fake ProductionBundle + StrategyRegistryService 脚手架。"""

from __future__ import annotations

from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import ProductionBundleSummary
from app.services.research_data.registry import LocalJsonRegistry
from app.services.strategy_registry.runner import StrategyRegistryService
from app.services.trading_governance.runner import TradingGovernanceService

STRATEGY_CODE = "reg_strat_alpha"
STRATEGY_VERSION = "sv_reg_v1"
STRATEGY_HASH = "sh_reg_golden_001"
BUNDLE_HASH = "pb_reg_golden_001"
DATASET_HASH = "dh_reg_golden"
MODEL_VERSION = "mv_reg_1"
FEATURE_VERSION = "fv_reg_1"
SNAPSHOT_ID = "snap_reg_1"
RISK_REF = "risk_default@v1"


def fake_production_bundle() -> ProductionBundleSummary:
    """最小 APPROVED ProductionBundle，无需真实 R2。"""
    return ProductionBundleSummary(
        bundle_hash=BUNDLE_HASH,
        strategy_hash=STRATEGY_HASH,
        strategy_code=STRATEGY_CODE,
        cv_hash="cv_reg_golden",
        dataset_hash=DATASET_HASH,
        snapshot_id=SNAPSHOT_ID,
        model_version=MODEL_VERSION,
        model_artifact_id="maid_reg_1",
        processor_hash="ph_reg_1",
        feature_hashes=[FEATURE_VERSION],
        execution_policy="NEXT_OPEN",
        status="APPROVED",
        metadata={"processor_version": "pv_reg_1"},
    )


def make_registry_env(
    tmp: Path,
) -> tuple[StrategyRegistryService, LocalJsonRegistry, TradingGovernanceService]:
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    registry.upsert_production_bundle(fake_production_bundle())
    gov = TradingGovernanceService(store, registry)
    svc = StrategyRegistryService(store, registry, governance=gov)
    return svc, registry, gov
