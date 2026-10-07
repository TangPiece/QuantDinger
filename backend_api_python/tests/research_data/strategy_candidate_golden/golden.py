"""Phase 8B Golden：Fake Research 证据 + StrategyCandidateService 脚手架。"""

from __future__ import annotations

from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import (
    ExperimentDefinition,
    ResearchBacktestSummary,
    StrategyResearchSummary,
)
from app.services.research_data.registry import LocalJsonRegistry
from app.services.strategy_candidate.runner import StrategyCandidateService
from app.services.strategy_registry.runner import StrategyRegistryService

STRATEGY_CODE = "cand_strat_alpha"
CAND_VERSION = "cv8b_v1"
STRATEGY_HASH = "sh_cand_golden_001"
BACKTEST_HASH = "bt_cand_golden_001"
EXPERIMENT_ID = "exp_cand_golden_001"
DATASET_HASH = "dh_cand_golden"
MODEL_VERSION = "mv_cand_1"
FEATURE_VERSION = "feat_cand@v1"
SNAPSHOT_ID = "snap_cand_1"
EVALUATION_HASH = "eval_cand_1"
CV_HASH = "cv_cand_1"
REGISTRY_VERSION = "sv_from_cand_v1"


def fake_experiment() -> ExperimentDefinition:
    return ExperimentDefinition(
        experiment_id=EXPERIMENT_ID,
        name="phase8b golden experiment",
        dataset_ref="ds_golden@v1",
        snapshot_id=SNAPSHOT_ID,
        dataset_hash=DATASET_HASH,
        model_version_ref=f"model@{MODEL_VERSION}",
        model_artifact_id="maid_cand_1",
        feature_refs=[FEATURE_VERSION],
        processor_ref="proc_cand@v1",
        parameters={},
        status="COMPLETED",
    )


def fake_strategy_research() -> StrategyResearchSummary:
    return StrategyResearchSummary(
        strategy_hash=STRATEGY_HASH,
        strategy_code=STRATEGY_CODE,
        evaluation_hash=EVALUATION_HASH,
        snapshot_id=SNAPSHOT_ID,
        signal_definition_json={"signal": "golden"},
        rebalance_rule_json={"freq": "DAILY"},
        holding_rule_json={"max_hold": 5},
        metadata={"model_version": MODEL_VERSION},
    )


def fake_backtest() -> ResearchBacktestSummary:
    return ResearchBacktestSummary(
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
        start_date="2024-01-01",
        end_date="2024-06-30",
        execution_policy="NEXT_OPEN",
        metadata={"cv_hash": CV_HASH, "risk_policy_ref": "risk_default@v1"},
    )


def seed_research_evidence(registry: LocalJsonRegistry) -> None:
    registry.upsert_experiment(fake_experiment())
    registry.upsert_strategy_research(fake_strategy_research())
    registry.upsert_research_backtest(fake_backtest())


def make_candidate_env(
    tmp: Path,
) -> tuple[StrategyCandidateService, StrategyRegistryService, LocalJsonRegistry]:
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    seed_research_evidence(registry)
    reg_svc = StrategyRegistryService(store, registry)
    cand_svc = StrategyCandidateService(store, registry, strategy_registry=reg_svc)
    return cand_svc, reg_svc, registry
