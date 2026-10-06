"""研究 Registry：D1 qd_research，未配置时用本地 JSON 供单测。"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from . import config, d1_client
from .contracts import (
    ArtifactRecord,
    ConsistencyRunRecord,
    DataVersionRef,
    DatasetDefinition,
    DatasetHandle,
    EvaluationDatasetRecord,
    ExperimentDefinition,
    FactorCombinationSummary,
    FactorDatasetRecord,
    FactorPortfolioSummary,
    FactorEvaluationSummary,
    FactorNeutralizationSummary,
    FactorStabilitySummary,
    FeatureDefinition,
    GroupEvaluationSummary,
    ModelDefinition,
    ModelVersionRecord,
    PricePolicy,
    ProcessorDefinition,
    CrossValidationSummary,
    ProductionBundleSummary,
    ProductionDeploymentRunSummary,
    ProductionDeploymentSummary,
    ProductionRuntimeEventRecord,
    ProductionRuntimeRunSummary,
    ProductionRuntimeSummary,
    ProductionAccountSummary,
    ProductionPortfolioApplySummary,
    ProductionPortfolioSnapshotSummary,
    ProductionPortfolioSummary,
    ProductionPositionEventRecord,
    ProductionPositionSummary,
    RiskDecisionEventRecord,
    RiskPolicySummary,
    RiskRunSummary,
    OmsFillSummary,
    OmsOrderEventRecord,
    OmsOrderSummary,
    OmsOutboxRecord,
    BrokerEventIndexRecord,
    BrokerOrderLinkRecord,
    BrokerSessionSummary,
    BrokerSnapshotIndexRecord,
    ReconciliationCursorRecord,
    ReconciliationFindingSummary,
    ReconciliationGateRecord,
    ReconciliationRunSummary,
    QlibRunSummary,
    ResearchBacktestSummary,
    ResearchStrategyRecord,
    SignalRunRecord,
    SnapshotRef,
    StrategyResearchSummary,
)
from .hashing import canonical_json, compute_dataset_hash


class ProcessorImmutabilityError(ValueError):
    """同一 code@version 禁止修改 pipeline；须 bump version。"""


class FeatureImmutabilityError(ValueError):
    """同一 feature code@version 禁止修改定义；须 bump version。"""


class ModelImmutabilityError(ValueError):
    """同一 model code@version 禁止修改 config；须 bump version。"""


def _assert_model_version_immutable(
    existing_raw: dict[str, Any],
    record: ModelVersionRecord,
) -> None:
    """已存在的 model_version 若 config 变化则拒绝。"""
    old_cfg = existing_raw.get("config") if isinstance(existing_raw, dict) else None
    new_cfg = record.model_dump(mode="json").get("config")
    if canonical_json(old_cfg or {}) != canonical_json(new_cfg or {}):
        raise ModelImmutabilityError(
            f"model version {record.model_code}@{record.version} is immutable; "
            "bump version to change config"
        )


def _assert_processor_immutable(
    existing_raw: dict[str, Any],
    processor: ProcessorDefinition,
) -> None:
    """已存在的 processor 若 pipeline 内容变化则拒绝。"""
    old_pipe = existing_raw.get("pipeline") if isinstance(existing_raw, dict) else None
    new_pipe = processor.model_dump(mode="json").get("pipeline")
    if canonical_json(old_pipe or []) != canonical_json(new_pipe or []):
        raise ProcessorImmutabilityError(
            f"processor {processor.code}@{processor.version} is immutable; "
            "bump version to change pipeline"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ResearchRegistry(Protocol):
    def upsert_data_version(
        self,
        *,
        dataset_code: str,
        version: str,
        schema_version: str,
        status: str,
        checksum: str,
        r2_uri: str,
        row_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int: ...

    def create_snapshot(
        self,
        *,
        snapshot_id: str,
        name: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str: ...

    def upsert_dataset(
        self, definition: DatasetDefinition, *, status: str = "ACTIVE"
    ) -> None: ...

    def get_dataset(self, dataset_ref: str) -> DatasetHandle: ...

    def upsert_feature(self, feature: FeatureDefinition) -> None: ...

    def get_feature(self, feature_ref: str) -> FeatureDefinition: ...

    def upsert_processor(self, processor: ProcessorDefinition) -> None: ...

    def get_processor(self, processor_ref: str) -> ProcessorDefinition: ...

    def upsert_universe_ref(
        self,
        *,
        universe_code: str,
        pg_universe_id: int | None,
        market: str | None,
    ) -> None: ...

    def get_snapshot(self, snapshot_id: str) -> SnapshotRef: ...

    def upsert_model(self, model: ModelDefinition) -> None: ...

    def get_model(self, model_code: str) -> ModelDefinition: ...

    def upsert_model_version(self, record: ModelVersionRecord) -> None: ...

    def get_model_version(self, model_version_ref: str) -> ModelVersionRecord: ...

    def upsert_artifact(self, record: ArtifactRecord) -> None: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord: ...

    def upsert_experiment(self, experiment: ExperimentDefinition) -> None: ...

    def get_experiment(self, experiment_id: str) -> ExperimentDefinition: ...

    def upsert_signal_run(self, record: SignalRunRecord) -> None: ...

    def get_signal_run(self, signal_run_id: str) -> SignalRunRecord: ...

    def upsert_consistency_run(self, record: ConsistencyRunRecord) -> None: ...

    def get_consistency_run(self, run_id: str) -> ConsistencyRunRecord: ...

    def upsert_factor_dataset(self, record: FactorDatasetRecord) -> None: ...

    def get_factor_dataset(self, factor_dataset_id: str) -> FactorDatasetRecord: ...

    def upsert_evaluation_dataset(self, record: EvaluationDatasetRecord) -> None: ...

    def get_evaluation_dataset(self, evaluation_hash: str) -> EvaluationDatasetRecord: ...

    def upsert_factor_evaluation_summary(
        self, record: FactorEvaluationSummary
    ) -> None: ...

    def get_factor_evaluation_summary(
        self, metric_hash: str, horizon: int
    ) -> FactorEvaluationSummary: ...

    def upsert_factor_group_evaluation(
        self, record: GroupEvaluationSummary
    ) -> None: ...

    def get_factor_group_evaluation(
        self, group_evaluation_hash: str, horizon: int
    ) -> GroupEvaluationSummary: ...

    def upsert_factor_stability_evaluation(
        self, record: FactorStabilitySummary
    ) -> None: ...

    def get_factor_stability_evaluation(
        self, stability_hash: str, horizon: int
    ) -> FactorStabilitySummary: ...

    def upsert_factor_neutralization(
        self, record: FactorNeutralizationSummary
    ) -> None: ...

    def get_factor_neutralization(
        self, neutralization_hash: str
    ) -> FactorNeutralizationSummary: ...

    def upsert_factor_combination(
        self, record: FactorCombinationSummary
    ) -> None: ...

    def get_factor_combination(
        self, combination_hash: str
    ) -> FactorCombinationSummary: ...

    def upsert_factor_portfolio(
        self, record: FactorPortfolioSummary
    ) -> None: ...

    def get_factor_portfolio(
        self, portfolio_hash: str
    ) -> FactorPortfolioSummary: ...

    def upsert_research_strategy(
        self, record: ResearchStrategyRecord
    ) -> None: ...

    def get_research_strategy(
        self, strategy_code: str
    ) -> ResearchStrategyRecord: ...

    def upsert_strategy_research(
        self, record: StrategyResearchSummary
    ) -> None: ...

    def get_strategy_research(
        self, strategy_hash: str
    ) -> StrategyResearchSummary: ...

    def upsert_research_backtest(
        self, record: ResearchBacktestSummary
    ) -> None: ...

    def get_research_backtest(
        self, backtest_hash: str
    ) -> ResearchBacktestSummary: ...

    def upsert_research_qlib_run(self, record: QlibRunSummary) -> None: ...

    def get_research_qlib_run(self, qlib_run_hash: str) -> QlibRunSummary: ...

    def upsert_research_cross_validation(
        self, record: CrossValidationSummary
    ) -> None: ...

    def get_research_cross_validation(
        self, cv_hash: str
    ) -> CrossValidationSummary: ...

    def upsert_production_bundle(
        self, record: ProductionBundleSummary
    ) -> None: ...

    def get_production_bundle(
        self, bundle_hash: str
    ) -> ProductionBundleSummary: ...

    def upsert_production_deployment(
        self, record: ProductionDeploymentSummary
    ) -> None: ...

    def get_production_deployment(
        self, deployment_id: str
    ) -> ProductionDeploymentSummary: ...

    def get_active_deployment(
        self, strategy_code: str
    ) -> ProductionDeploymentSummary: ...

    def upsert_deployment_run(
        self, record: ProductionDeploymentRunSummary
    ) -> None: ...

    def get_deployment_run(
        self, run_id: str
    ) -> ProductionDeploymentRunSummary: ...

    def upsert_production_runtime(
        self, record: ProductionRuntimeSummary
    ) -> None: ...

    def get_production_runtime(
        self, runtime_id: str
    ) -> ProductionRuntimeSummary: ...

    def append_runtime_event(
        self, record: ProductionRuntimeEventRecord
    ) -> None: ...

    def list_runtime_events(
        self, runtime_id: str, *, limit: int = 200
    ) -> list[ProductionRuntimeEventRecord]: ...

    def upsert_runtime_run(
        self, record: ProductionRuntimeRunSummary
    ) -> None: ...

    def get_runtime_run_by_idempotency(
        self, idempotency_key: str
    ) -> ProductionRuntimeRunSummary: ...

    def get_runtime_run(self, run_id: str) -> ProductionRuntimeRunSummary: ...

    def upsert_production_account(
        self, record: ProductionAccountSummary
    ) -> None: ...

    def get_production_account(
        self, account_id: str
    ) -> ProductionAccountSummary: ...

    def upsert_production_portfolio(
        self, record: ProductionPortfolioSummary
    ) -> None: ...

    def get_production_portfolio(
        self, portfolio_id: str
    ) -> ProductionPortfolioSummary: ...

    def list_portfolios_by_account(
        self, account_id: str
    ) -> list[ProductionPortfolioSummary]: ...

    def upsert_production_position(
        self, record: ProductionPositionSummary
    ) -> None: ...

    def list_positions(
        self, portfolio_id: str
    ) -> list[ProductionPositionSummary]: ...

    def append_position_event(
        self, record: ProductionPositionEventRecord
    ) -> None: ...

    def list_position_events(
        self, portfolio_id: str, *, limit: int = 500
    ) -> list[ProductionPositionEventRecord]: ...

    def upsert_portfolio_snapshot(
        self, record: ProductionPortfolioSnapshotSummary
    ) -> None: ...

    def get_portfolio_snapshot(
        self, snapshot_id: str
    ) -> ProductionPortfolioSnapshotSummary: ...

    def upsert_portfolio_apply(
        self, record: ProductionPortfolioApplySummary
    ) -> None: ...

    def get_apply_by_idempotency(
        self, idempotency_key: str
    ) -> ProductionPortfolioApplySummary: ...

    def upsert_risk_policy(self, record: RiskPolicySummary) -> None: ...

    def get_risk_policy(
        self, policy_code: str, policy_version: str
    ) -> RiskPolicySummary: ...

    def get_risk_policy_by_hash(self, policy_hash: str) -> RiskPolicySummary: ...

    def upsert_risk_run(self, record: RiskRunSummary) -> None: ...

    def get_risk_run_by_idempotency(
        self, idempotency_key: str
    ) -> RiskRunSummary: ...

    def get_risk_run(self, risk_run_id: str) -> RiskRunSummary: ...

    def append_risk_decision_event(
        self, record: RiskDecisionEventRecord
    ) -> None: ...

    def upsert_oms_order(self, record: OmsOrderSummary) -> None: ...

    def get_oms_order(self, order_id: str) -> OmsOrderSummary: ...

    def get_order_by_idempotency(self, idempotency_key: str) -> OmsOrderSummary: ...

    def list_oms_orders(
        self, *, account_id: str = "", status: str = ""
    ) -> list[OmsOrderSummary]: ...

    def upsert_oms_order_version(self, version: Any) -> None: ...

    def append_order_event(self, record: OmsOrderEventRecord) -> None: ...

    def list_order_events(self, order_id: str) -> list[OmsOrderEventRecord]: ...

    def upsert_fill(self, record: OmsFillSummary) -> None: ...

    def list_oms_fills(self, order_id: str) -> list[OmsFillSummary]: ...

    def enqueue_outbox(self, record: OmsOutboxRecord) -> None: ...

    def list_outbox(self, *, limit: int = 100) -> list[OmsOutboxRecord]: ...

    def mark_outbox(self, outbox_id: str, status: str) -> None: ...

    def upsert_cancel_request(self, request: Any) -> None: ...

    def upsert_replace_request(self, request: Any) -> None: ...

    def upsert_broker_session(self, record: BrokerSessionSummary) -> None: ...

    def upsert_broker_order_link(self, record: BrokerOrderLinkRecord) -> None: ...

    def get_order_link_by_client_id(
        self, client_order_id: str
    ) -> BrokerOrderLinkRecord: ...

    def get_order_link_by_broker_id(
        self, broker_id: str, broker_order_id: str
    ) -> BrokerOrderLinkRecord: ...

    def try_record_execution_dedup(
        self, broker_id: str, broker_execution_id: str
    ) -> bool: ...

    def append_broker_event_index(
        self, record: BrokerEventIndexRecord
    ) -> None: ...

    def upsert_reconciliation_run(
        self, record: ReconciliationRunSummary
    ) -> None: ...

    def upsert_reconciliation_finding(
        self, record: ReconciliationFindingSummary
    ) -> None: ...

    def list_reconciliation_findings(
        self,
        *,
        run_id: str = "",
        account_id: str = "",
        status: str = "",
    ) -> list[ReconciliationFindingSummary]: ...

    def append_broker_snapshot_index(
        self, record: BrokerSnapshotIndexRecord
    ) -> None: ...

    def get_reconciliation_cursor(
        self,
        account_id: str,
        *,
        broker_id: str = "",
        cursor_type: str = "EXECUTION",
    ) -> ReconciliationCursorRecord: ...

    def set_reconciliation_cursor(
        self, record: ReconciliationCursorRecord
    ) -> None: ...

    def get_reconciliation_gate(
        self, account_id: str
    ) -> ReconciliationGateRecord: ...

    def set_reconciliation_gate(
        self, record: ReconciliationGateRecord
    ) -> None: ...


class LocalJsonRegistry:
    """本地 JSON Registry，测试默认后端。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or config.research_cache_dir() / "registry")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._path = self.root / "registry.json"
        if not self._path.is_file():
            self._write(
                {
                    "data_versions": {},
                    "snapshots": {},
                    "datasets": {},
                    "features": {},
                    "processors": {},
                    "models": {},
                    "model_versions": {},
                    "artifacts": {},
                    "experiments": {},
                    "signal_runs": {},
                    "consistency_runs": {},
                    "factor_datasets": {},
                    "evaluation_datasets": {},
                    "factor_evaluation_summaries": {},
                    "factor_group_evaluations": {},
                    "factor_stability_evaluations": {},
                    "factor_neutralizations": {},
                    "factor_combinations": {},
                    "factor_portfolios": {},
                    "research_strategies": {},
                    "strategy_research": {},
                    "research_backtests": {},
                    "research_qlib_runs": {},
                    "research_cross_validations": {},
                    "production_bundles": {},
                    "production_deployments": {},
                    "production_deployment_runs": {},
                    "production_runtimes": {},
                    "production_runtime_events": {},
                    "production_runtime_runs": {},
                    "production_runtime_runs_by_idempotency": {},
                    "production_accounts": {},
                    "production_portfolios": {},
                    "production_positions": {},
                    "production_position_events": {},
                    "production_portfolio_snapshots": {},
                    "production_portfolio_applies": {},
                    "production_portfolio_applies_by_idempotency": {},
                    "risk_policies": {},
                    "risk_policies_by_ref": {},
                    "risk_runs": {},
                    "risk_runs_by_idempotency": {},
                    "risk_decision_events": {},
                    "universe_refs": {},
                    "_seq": 0,
                }
            )

    def _read(self) -> dict[str, Any]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert_data_version(
        self,
        *,
        dataset_code: str,
        version: str,
        schema_version: str,
        status: str,
        checksum: str,
        r2_uri: str,
        row_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self._lock:
            data = self._read()
            key = f"{dataset_code}@{version}"
            seq = int(data.get("_seq") or 0) + 1
            data["_seq"] = seq
            data["data_versions"][key] = {
                "data_version_id": seq,
                "dataset_code": dataset_code,
                "version": version,
                "schema_version": schema_version,
                "status": status,
                "checksum": checksum,
                "r2_uri": r2_uri,
                "row_count": row_count,
                "metadata": metadata or {},
                "created_at": _utc_now(),
            }
            self._write(data)
            return seq

    def create_snapshot(
        self,
        *,
        snapshot_id: str,
        name: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        with self._lock:
            data = self._read()
            data["snapshots"][snapshot_id] = {
                "snapshot_id": snapshot_id,
                "name": name,
                "created_at": _utc_now(),
                "metadata": metadata or {},
                "items": items,
            }
            self._write(data)
            return snapshot_id

    def upsert_dataset(
        self, definition: DatasetDefinition, *, status: str = "ACTIVE"
    ) -> None:
        """登记 Dataset；status 存旁路字段（Local JSON），供 validated 等验收态。"""
        with self._lock:
            data = self._read()
            key = f"{definition.code}@{definition.version}"
            payload = definition.model_dump(mode="json")
            # Domain Contract 无 status 字段；Registry 侧单独记录
            payload["_registry_status"] = status
            data["datasets"][key] = payload
            self._write(data)

    def get_dataset(self, dataset_ref: str) -> DatasetHandle:
        code, version = _split_ref(dataset_ref)
        data = self._read()
        raw = data["datasets"].get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"dataset not found: {dataset_ref}")
        # 剥离 Registry 旁路字段，避免 DatasetDefinition extra=forbid 失败
        payload = {k: v for k, v in raw.items() if not str(k).startswith("_")}
        definition = DatasetDefinition.model_validate(payload)
        snapshot = self.get_snapshot(definition.snapshot_id)
        digest = compute_dataset_hash(
            dataset_definition=definition.model_dump(mode="json"),
            dataset_version=definition.version,
            snapshot_id=definition.snapshot_id,
            schema_version=definition.schema_version,
            processor_version=definition.processor or "",
            materializer_version="none",
            price_policy=definition.price_policy.model_dump(mode="json"),
        )
        return DatasetHandle(
            definition=definition,
            snapshot=snapshot,
            dataset_hash=digest,
            manifest_uri="",
        )

    def upsert_feature(self, feature: FeatureDefinition) -> None:
        """登记 Feature/Factor；同 code@version 且 factor_hash 变化则拒绝。"""
        from app.services.research_data.factor_lab.hash import compute_factor_hash
        from app.services.research_data.factor_lab.immutability import (
            FeatureImmutabilityError as _FIE,
            assert_feature_immutable,
            ensure_factor_hash,
        )

        feat = ensure_factor_hash(feature)
        feat = feat.model_copy(update={"factor_hash": compute_factor_hash(feat)})
        with self._lock:
            data = self._read()
            data.setdefault("features", {})
            key = f"{feat.code}@{feat.version}"
            existing = data["features"].get(key)
            if existing is not None:
                try:
                    assert_feature_immutable(existing, feat)
                except _FIE as exc:
                    raise FeatureImmutabilityError(str(exc)) from exc
                return
            data["features"][key] = feat.model_dump(mode="json")
            self._write(data)

    def get_feature(self, feature_ref: str) -> FeatureDefinition:
        code, version = _split_ref(feature_ref)
        data = self._read()
        raw = data["features"].get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"feature not found: {feature_ref}")
        return FeatureDefinition.model_validate(raw)

    def upsert_processor(self, processor: ProcessorDefinition) -> None:
        """登记 ProcessorDefinition；同 code@version 禁止改 pipeline。"""
        with self._lock:
            data = self._read()
            data.setdefault("processors", {})
            key = f"{processor.code}@{processor.version}"
            existing = data["processors"].get(key)
            if existing is not None:
                _assert_processor_immutable(existing, processor)
                return  # 幂等：内容相同则跳过
            data["processors"][key] = processor.model_dump(mode="json")
            self._write(data)

    def get_processor(self, processor_ref: str) -> ProcessorDefinition:
        """读取 `code@version` Processor。"""
        code, version = _split_ref(processor_ref)
        data = self._read()
        raw = (data.get("processors") or {}).get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"processor not found: {processor_ref}")
        return ProcessorDefinition.model_validate(raw)

    def upsert_universe_ref(
        self,
        *,
        universe_code: str,
        pg_universe_id: int | None,
        market: str | None,
    ) -> None:
        with self._lock:
            data = self._read()
            data["universe_refs"][universe_code] = {
                "universe_code": universe_code,
                "pg_universe_id": pg_universe_id,
                "market": market,
                "synced_at": _utc_now(),
            }
            self._write(data)

    def get_snapshot(self, snapshot_id: str) -> SnapshotRef:
        data = self._read()
        raw = data["snapshots"].get(snapshot_id)
        if not raw:
            raise KeyError(f"snapshot not found: {snapshot_id}")
        items = [
            DataVersionRef(
                dataset_code=str(item.get("dataset_code") or ""),
                version=str(item.get("version") or ""),
                checksum=item.get("checksum"),
                r2_uri=item.get("path") or item.get("r2_uri"),
            )
            for item in (raw.get("items") or [])
        ]
        return SnapshotRef(snapshot_id=snapshot_id, items=items)

    def upsert_model(self, model: ModelDefinition) -> None:
        """登记 ModelDefinition（engine 等元数据）。"""
        with self._lock:
            data = self._read()
            data.setdefault("models", {})
            key = model.code
            existing = data["models"].get(key)
            payload = model.model_dump(mode="json")
            if existing is not None and existing != payload:
                raise ModelImmutabilityError(
                    f"model {key!r} metadata conflict; bump code or align definition"
                )
            data["models"][key] = payload
            self._write(data)

    def get_model(self, model_code: str) -> ModelDefinition:
        data = self._read()
        raw = (data.get("models") or {}).get(model_code)
        if not raw:
            raise KeyError(f"model not found: {model_code!r}")
        return ModelDefinition.model_validate(raw)

    def upsert_model_version(self, record: ModelVersionRecord) -> None:
        """登记 model_version；同 code@version 禁止改 config。"""
        with self._lock:
            data = self._read()
            data.setdefault("model_versions", {})
            key = f"{record.model_code}@{record.version}"
            existing = data["model_versions"].get(key)
            if existing is not None:
                _assert_model_version_immutable(existing, record)
                # 允许更新 artifact_id / metrics（训练产物）
                merged = dict(existing)
                merged.update(record.model_dump(mode="json"))
                data["model_versions"][key] = merged
            else:
                data["model_versions"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_model_version(self, model_version_ref: str) -> ModelVersionRecord:
        code, version = _split_ref(model_version_ref)
        data = self._read()
        raw = (data.get("model_versions") or {}).get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"model_version not found: {model_version_ref}")
        return ModelVersionRecord.model_validate(raw)

    def upsert_artifact(self, record: ArtifactRecord) -> None:
        """登记 artifact 索引（内容寻址 id）。"""
        with self._lock:
            data = self._read()
            data.setdefault("artifacts", {})
            existing = data["artifacts"].get(record.artifact_id)
            if existing is not None and existing != record.model_dump(mode="json"):
                raise ValueError(f"artifact_id conflict: {record.artifact_id!r}")
            data["artifacts"][record.artifact_id] = record.model_dump(mode="json")
            self._write(data)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        data = self._read()
        raw = (data.get("artifacts") or {}).get(artifact_id)
        if not raw:
            raise KeyError(f"artifact not found: {artifact_id!r}")
        return ArtifactRecord.model_validate(raw)

    def upsert_experiment(self, experiment: ExperimentDefinition) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("experiments", {})
            data["experiments"][experiment.experiment_id] = experiment.model_dump(mode="json")
            self._write(data)

    def get_experiment(self, experiment_id: str) -> ExperimentDefinition:
        data = self._read()
        raw = (data.get("experiments") or {}).get(experiment_id)
        if not raw:
            raise KeyError(f"experiment not found: {experiment_id!r}")
        return ExperimentDefinition.model_validate(raw)

    def upsert_signal_run(self, record: SignalRunRecord) -> None:
        """登记一次 Signal 管线运行（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("signal_runs", {})
            data["signal_runs"][record.signal_run_id] = record.model_dump(mode="json")
            self._write(data)

    def get_signal_run(self, signal_run_id: str) -> SignalRunRecord:
        data = self._read()
        raw = (data.get("signal_runs") or {}).get(signal_run_id)
        if not raw:
            raise KeyError(f"signal_run not found: {signal_run_id!r}")
        return SignalRunRecord.model_validate(raw)

    def upsert_consistency_run(self, record: ConsistencyRunRecord) -> None:
        """登记一次双引擎一致性运行（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("consistency_runs", {})
            data["consistency_runs"][record.run_id] = record.model_dump(mode="json")
            self._write(data)

    def get_consistency_run(self, run_id: str) -> ConsistencyRunRecord:
        data = self._read()
        raw = (data.get("consistency_runs") or {}).get(run_id)
        if not raw:
            raise KeyError(f"consistency_run not found: {run_id!r}")
        return ConsistencyRunRecord.model_validate(raw)

    def upsert_factor_dataset(self, record: FactorDatasetRecord) -> None:
        """登记 Factor Dataset 索引（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("factor_datasets", {})
            data["factor_datasets"][record.factor_dataset_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_factor_dataset(self, factor_dataset_id: str) -> FactorDatasetRecord:
        data = self._read()
        raw = (data.get("factor_datasets") or {}).get(factor_dataset_id)
        if not raw:
            raise KeyError(f"factor_dataset not found: {factor_dataset_id!r}")
        return FactorDatasetRecord.model_validate(raw)

    def upsert_evaluation_dataset(self, record: EvaluationDatasetRecord) -> None:
        """登记 Evaluation Dataset 索引（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("evaluation_datasets", {})
            data["evaluation_datasets"][record.evaluation_hash] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_evaluation_dataset(self, evaluation_hash: str) -> EvaluationDatasetRecord:
        data = self._read()
        raw = (data.get("evaluation_datasets") or {}).get(evaluation_hash)
        if not raw:
            raise KeyError(f"evaluation_dataset not found: {evaluation_hash!r}")
        return EvaluationDatasetRecord.model_validate(raw)

    def upsert_factor_evaluation_summary(
        self, record: FactorEvaluationSummary
    ) -> None:
        """登记 IC Summary（Local JSON；key = metric_hash:horizon）。"""
        key = f"{record.metric_hash}:{int(record.horizon)}"
        with self._lock:
            data = self._read()
            data.setdefault("factor_evaluation_summaries", {})
            data["factor_evaluation_summaries"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_evaluation_summary(
        self, metric_hash: str, horizon: int
    ) -> FactorEvaluationSummary:
        data = self._read()
        key = f"{metric_hash}:{int(horizon)}"
        raw = (data.get("factor_evaluation_summaries") or {}).get(key)
        if not raw:
            raise KeyError(
                f"factor_evaluation_summary not found: {metric_hash!r} h={horizon}"
            )
        return FactorEvaluationSummary.model_validate(raw)

    def upsert_factor_group_evaluation(
        self, record: GroupEvaluationSummary
    ) -> None:
        """登记 Group Evaluation Summary（Local JSON）。"""
        key = f"{record.group_evaluation_hash}:{int(record.horizon)}"
        with self._lock:
            data = self._read()
            data.setdefault("factor_group_evaluations", {})
            data["factor_group_evaluations"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_group_evaluation(
        self, group_evaluation_hash: str, horizon: int
    ) -> GroupEvaluationSummary:
        data = self._read()
        key = f"{group_evaluation_hash}:{int(horizon)}"
        raw = (data.get("factor_group_evaluations") or {}).get(key)
        if not raw:
            raise KeyError(
                f"factor_group_evaluation not found: {group_evaluation_hash!r} h={horizon}"
            )
        return GroupEvaluationSummary.model_validate(raw)

    def upsert_factor_stability_evaluation(
        self, record: FactorStabilitySummary
    ) -> None:
        """登记 Stability Summary（Local JSON）。"""
        key = f"{record.stability_hash}:{int(record.horizon)}"
        with self._lock:
            data = self._read()
            data.setdefault("factor_stability_evaluations", {})
            data["factor_stability_evaluations"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_stability_evaluation(
        self, stability_hash: str, horizon: int
    ) -> FactorStabilitySummary:
        data = self._read()
        key = f"{stability_hash}:{int(horizon)}"
        raw = (data.get("factor_stability_evaluations") or {}).get(key)
        if not raw:
            raise KeyError(
                f"factor_stability_evaluation not found: {stability_hash!r} h={horizon}"
            )
        return FactorStabilitySummary.model_validate(raw)

    def upsert_factor_neutralization(
        self, record: FactorNeutralizationSummary
    ) -> None:
        """登记 Neutralization Summary（Local JSON）。"""
        key = record.neutralization_hash
        with self._lock:
            data = self._read()
            data.setdefault("factor_neutralizations", {})
            data["factor_neutralizations"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_neutralization(
        self, neutralization_hash: str
    ) -> FactorNeutralizationSummary:
        data = self._read()
        raw = (data.get("factor_neutralizations") or {}).get(neutralization_hash)
        if not raw:
            raise KeyError(
                f"factor_neutralization not found: {neutralization_hash!r}"
            )
        return FactorNeutralizationSummary.model_validate(raw)

    def upsert_factor_combination(
        self, record: FactorCombinationSummary
    ) -> None:
        """登记 Combination Summary（Local JSON）。"""
        key = record.combination_hash
        with self._lock:
            data = self._read()
            data.setdefault("factor_combinations", {})
            data["factor_combinations"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_combination(
        self, combination_hash: str
    ) -> FactorCombinationSummary:
        data = self._read()
        raw = (data.get("factor_combinations") or {}).get(combination_hash)
        if not raw:
            raise KeyError(f"factor_combination not found: {combination_hash!r}")
        return FactorCombinationSummary.model_validate(raw)

    def upsert_factor_portfolio(self, record: FactorPortfolioSummary) -> None:
        """登记 Portfolio Summary（Local JSON）。"""
        key = record.portfolio_hash
        with self._lock:
            data = self._read()
            data.setdefault("factor_portfolios", {})
            data["factor_portfolios"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_portfolio(self, portfolio_hash: str) -> FactorPortfolioSummary:
        data = self._read()
        raw = (data.get("factor_portfolios") or {}).get(portfolio_hash)
        if not raw:
            raise KeyError(f"factor_portfolio not found: {portfolio_hash!r}")
        return FactorPortfolioSummary.model_validate(raw)

    def upsert_research_strategy(self, record: ResearchStrategyRecord) -> None:
        """登记研究策略名录（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("research_strategies", {})
            data["research_strategies"][record.strategy_code] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_research_strategy(self, strategy_code: str) -> ResearchStrategyRecord:
        data = self._read()
        raw = (data.get("research_strategies") or {}).get(strategy_code)
        if not raw:
            raise KeyError(f"research_strategy not found: {strategy_code!r}")
        return ResearchStrategyRecord.model_validate(raw)

    def upsert_strategy_research(self, record: StrategyResearchSummary) -> None:
        """登记冻结策略版本 Summary（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("strategy_research", {})
            data["strategy_research"][record.strategy_hash] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_strategy_research(self, strategy_hash: str) -> StrategyResearchSummary:
        data = self._read()
        raw = (data.get("strategy_research") or {}).get(strategy_hash)
        if not raw:
            raise KeyError(f"strategy_research not found: {strategy_hash!r}")
        return StrategyResearchSummary.model_validate(raw)

    def upsert_research_backtest(self, record: ResearchBacktestSummary) -> None:
        """登记研究回测 Summary（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("research_backtests", {})
            data["research_backtests"][record.backtest_hash] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_research_backtest(self, backtest_hash: str) -> ResearchBacktestSummary:
        data = self._read()
        raw = (data.get("research_backtests") or {}).get(backtest_hash)
        if not raw:
            raise KeyError(f"research_backtest not found: {backtest_hash!r}")
        return ResearchBacktestSummary.model_validate(raw)

    def upsert_research_qlib_run(self, record: QlibRunSummary) -> None:
        """登记 Qlib Strategy Run Summary（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("research_qlib_runs", {})
            data["research_qlib_runs"][record.qlib_run_hash] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_research_qlib_run(self, qlib_run_hash: str) -> QlibRunSummary:
        data = self._read()
        raw = (data.get("research_qlib_runs") or {}).get(qlib_run_hash)
        if not raw:
            raise KeyError(f"research_qlib_run not found: {qlib_run_hash!r}")
        return QlibRunSummary.model_validate(raw)

    def upsert_research_cross_validation(
        self, record: CrossValidationSummary
    ) -> None:
        """登记 Cross Validation Summary（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("research_cross_validations", {})
            data["research_cross_validations"][record.cv_hash] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_research_cross_validation(self, cv_hash: str) -> CrossValidationSummary:
        data = self._read()
        raw = (data.get("research_cross_validations") or {}).get(cv_hash)
        if not raw:
            raise KeyError(f"research_cross_validation not found: {cv_hash!r}")
        return CrossValidationSummary.model_validate(raw)

    def upsert_production_bundle(self, record: ProductionBundleSummary) -> None:
        """登记 Production Bundle（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("production_bundles", {})
            data["production_bundles"][record.bundle_hash] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_production_bundle(self, bundle_hash: str) -> ProductionBundleSummary:
        data = self._read()
        raw = (data.get("production_bundles") or {}).get(bundle_hash)
        if not raw:
            raise KeyError(f"production_bundle not found: {bundle_hash!r}")
        return ProductionBundleSummary.model_validate(raw)

    def upsert_production_deployment(
        self, record: ProductionDeploymentSummary
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_deployments", {})
            data["production_deployments"][record.deployment_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_production_deployment(
        self, deployment_id: str
    ) -> ProductionDeploymentSummary:
        data = self._read()
        raw = (data.get("production_deployments") or {}).get(deployment_id)
        if not raw:
            raise KeyError(f"production_deployment not found: {deployment_id!r}")
        return ProductionDeploymentSummary.model_validate(raw)

    def get_active_deployment(
        self, strategy_code: str
    ) -> ProductionDeploymentSummary:
        data = self._read()
        deps = data.get("production_deployments") or {}
        # 取该 code 下最新 DEPLOYED
        candidates = [
            ProductionDeploymentSummary.model_validate(v)
            for v in deps.values()
            if v.get("strategy_code") == strategy_code
            and v.get("status") == "DEPLOYED"
        ]
        if not candidates:
            raise KeyError(f"active deployment not found: {strategy_code!r}")
        candidates.sort(key=lambda d: d.deployed_at or d.created_at or "")
        return candidates[-1]

    def upsert_deployment_run(
        self, record: ProductionDeploymentRunSummary
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_deployment_runs", {})
            data["production_deployment_runs"][record.run_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_deployment_run(self, run_id: str) -> ProductionDeploymentRunSummary:
        data = self._read()
        raw = (data.get("production_deployment_runs") or {}).get(run_id)
        if not raw:
            raise KeyError(f"deployment_run not found: {run_id!r}")
        return ProductionDeploymentRunSummary.model_validate(raw)

    def upsert_production_runtime(self, record: ProductionRuntimeSummary) -> None:
        """登记 Production Runtime 实例（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("production_runtimes", {})
            data["production_runtimes"][record.runtime_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_production_runtime(self, runtime_id: str) -> ProductionRuntimeSummary:
        data = self._read()
        raw = (data.get("production_runtimes") or {}).get(runtime_id)
        if not raw:
            raise KeyError(f"production_runtime not found: {runtime_id!r}")
        return ProductionRuntimeSummary.model_validate(raw)

    def append_runtime_event(self, record: ProductionRuntimeEventRecord) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_runtime_events", {})
            data["production_runtime_events"][record.event_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def list_runtime_events(
        self, runtime_id: str, *, limit: int = 200
    ) -> list[ProductionRuntimeEventRecord]:
        data = self._read()
        evs = data.get("production_runtime_events") or {}
        rows = [
            ProductionRuntimeEventRecord.model_validate(v)
            for v in evs.values()
            if v.get("runtime_id") == runtime_id
        ]
        rows.sort(key=lambda e: e.created_at or "")
        return rows[-int(limit) :]

    def upsert_runtime_run(self, record: ProductionRuntimeRunSummary) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_runtime_runs", {})
            data.setdefault("production_runtime_runs_by_idempotency", {})
            payload = record.model_dump(mode="json")
            data["production_runtime_runs"][record.run_id] = payload
            data["production_runtime_runs_by_idempotency"][
                record.idempotency_key
            ] = record.run_id
            self._write(data)

    def get_runtime_run_by_idempotency(
        self, idempotency_key: str
    ) -> ProductionRuntimeRunSummary:
        data = self._read()
        idx = data.get("production_runtime_runs_by_idempotency") or {}
        run_id = idx.get(idempotency_key)
        if not run_id:
            raise KeyError(f"runtime_run idempotency not found: {idempotency_key!r}")
        return self.get_runtime_run(run_id)

    def get_runtime_run(self, run_id: str) -> ProductionRuntimeRunSummary:
        data = self._read()
        raw = (data.get("production_runtime_runs") or {}).get(run_id)
        if not raw:
            raise KeyError(f"runtime_run not found: {run_id!r}")
        return ProductionRuntimeRunSummary.model_validate(raw)

    def upsert_production_account(self, record: ProductionAccountSummary) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_accounts", {})
            data["production_accounts"][record.account_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_production_account(self, account_id: str) -> ProductionAccountSummary:
        data = self._read()
        raw = (data.get("production_accounts") or {}).get(account_id)
        if not raw:
            raise KeyError(f"production_account not found: {account_id!r}")
        return ProductionAccountSummary.model_validate(raw)

    def upsert_production_portfolio(
        self, record: ProductionPortfolioSummary
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_portfolios", {})
            data["production_portfolios"][record.portfolio_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_production_portfolio(
        self, portfolio_id: str
    ) -> ProductionPortfolioSummary:
        data = self._read()
        raw = (data.get("production_portfolios") or {}).get(portfolio_id)
        if not raw:
            raise KeyError(f"production_portfolio not found: {portfolio_id!r}")
        return ProductionPortfolioSummary.model_validate(raw)

    def list_portfolios_by_account(
        self, account_id: str
    ) -> list[ProductionPortfolioSummary]:
        data = self._read()
        return [
            ProductionPortfolioSummary.model_validate(v)
            for v in (data.get("production_portfolios") or {}).values()
            if v.get("account_id") == account_id
        ]

    def upsert_production_position(
        self, record: ProductionPositionSummary
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_positions", {})
            key = f"{record.portfolio_id}|{record.instrument_key}"
            data["production_positions"][key] = record.model_dump(mode="json")
            self._write(data)

    def list_positions(
        self, portfolio_id: str
    ) -> list[ProductionPositionSummary]:
        data = self._read()
        return [
            ProductionPositionSummary.model_validate(v)
            for v in (data.get("production_positions") or {}).values()
            if v.get("portfolio_id") == portfolio_id
        ]

    def append_position_event(
        self, record: ProductionPositionEventRecord
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_position_events", {})
            data["production_position_events"][record.event_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def list_position_events(
        self, portfolio_id: str, *, limit: int = 500
    ) -> list[ProductionPositionEventRecord]:
        data = self._read()
        rows = [
            ProductionPositionEventRecord.model_validate(v)
            for v in (data.get("production_position_events") or {}).values()
            if v.get("portfolio_id") == portfolio_id
        ]
        rows.sort(key=lambda e: e.created_at or "")
        return rows[-int(limit) :]

    def upsert_portfolio_snapshot(
        self, record: ProductionPortfolioSnapshotSummary
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_portfolio_snapshots", {})
            data["production_portfolio_snapshots"][
                record.snapshot_id
            ] = record.model_dump(mode="json")
            self._write(data)

    def get_portfolio_snapshot(
        self, snapshot_id: str
    ) -> ProductionPortfolioSnapshotSummary:
        data = self._read()
        raw = (data.get("production_portfolio_snapshots") or {}).get(snapshot_id)
        if not raw:
            raise KeyError(f"portfolio_snapshot not found: {snapshot_id!r}")
        return ProductionPortfolioSnapshotSummary.model_validate(raw)

    def upsert_portfolio_apply(
        self, record: ProductionPortfolioApplySummary
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("production_portfolio_applies", {})
            data.setdefault("production_portfolio_applies_by_idempotency", {})
            payload = record.model_dump(mode="json")
            data["production_portfolio_applies"][record.apply_id] = payload
            data["production_portfolio_applies_by_idempotency"][
                record.idempotency_key
            ] = record.apply_id
            self._write(data)

    def get_apply_by_idempotency(
        self, idempotency_key: str
    ) -> ProductionPortfolioApplySummary:
        data = self._read()
        idx = data.get("production_portfolio_applies_by_idempotency") or {}
        apply_id = idx.get(idempotency_key)
        if not apply_id:
            raise KeyError(f"portfolio_apply idempotency not found: {idempotency_key!r}")
        raw = (data.get("production_portfolio_applies") or {}).get(apply_id)
        if not raw:
            raise KeyError(f"portfolio_apply not found: {apply_id!r}")
        return ProductionPortfolioApplySummary.model_validate(raw)

    def upsert_risk_policy(self, record: RiskPolicySummary) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("risk_policies", {})
            data.setdefault("risk_policies_by_ref", {})
            payload = record.model_dump(mode="json")
            data["risk_policies"][record.policy_hash] = payload
            data["risk_policies_by_ref"][
                f"{record.policy_code}@{record.policy_version}"
            ] = record.policy_hash
            self._write(data)

    def get_risk_policy(
        self, policy_code: str, policy_version: str
    ) -> RiskPolicySummary:
        data = self._read()
        ref = f"{policy_code}@{policy_version}"
        ph = (data.get("risk_policies_by_ref") or {}).get(ref)
        if not ph:
            raise KeyError(f"risk_policy not found: {ref!r}")
        return self.get_risk_policy_by_hash(ph)

    def get_risk_policy_by_hash(self, policy_hash: str) -> RiskPolicySummary:
        data = self._read()
        raw = (data.get("risk_policies") or {}).get(policy_hash)
        if not raw:
            raise KeyError(f"risk_policy not found: {policy_hash!r}")
        return RiskPolicySummary.model_validate(raw)

    def upsert_risk_run(self, record: RiskRunSummary) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("risk_runs", {})
            data.setdefault("risk_runs_by_idempotency", {})
            payload = record.model_dump(mode="json")
            data["risk_runs"][record.risk_run_id] = payload
            data["risk_runs_by_idempotency"][
                record.idempotency_key
            ] = record.risk_run_id
            self._write(data)

    def get_risk_run_by_idempotency(self, idempotency_key: str) -> RiskRunSummary:
        data = self._read()
        rid = (data.get("risk_runs_by_idempotency") or {}).get(idempotency_key)
        if not rid:
            raise KeyError(f"risk_run idempotency not found: {idempotency_key!r}")
        return self.get_risk_run(rid)

    def get_risk_run(self, risk_run_id: str) -> RiskRunSummary:
        data = self._read()
        raw = (data.get("risk_runs") or {}).get(risk_run_id)
        if not raw:
            raise KeyError(f"risk_run not found: {risk_run_id!r}")
        return RiskRunSummary.model_validate(raw)

    def append_risk_decision_event(
        self, record: RiskDecisionEventRecord
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("risk_decision_events", {})
            data["risk_decision_events"][record.event_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def upsert_oms_order(self, record: OmsOrderSummary) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("oms_orders", {})
            data.setdefault("oms_orders_by_idempotency", {})
            data.setdefault("oms_orders_by_client", {})
            payload = record.model_dump(mode="json")
            data["oms_orders"][record.order_id] = payload
            data["oms_orders_by_idempotency"][record.idempotency_key] = record.order_id
            data["oms_orders_by_client"][record.client_order_id] = record.order_id
            self._write(data)

    def get_oms_order(self, order_id: str) -> OmsOrderSummary:
        data = self._read()
        raw = (data.get("oms_orders") or {}).get(order_id)
        if not raw:
            raise KeyError(f"oms_order not found: {order_id!r}")
        return OmsOrderSummary.model_validate(raw)

    def get_order_by_idempotency(self, idempotency_key: str) -> OmsOrderSummary:
        data = self._read()
        oid = (data.get("oms_orders_by_idempotency") or {}).get(idempotency_key)
        if not oid:
            raise KeyError(f"oms idempotency not found: {idempotency_key!r}")
        return self.get_oms_order(oid)

    def list_oms_orders(
        self, *, account_id: str = "", status: str = ""
    ) -> list[OmsOrderSummary]:
        data = self._read()
        out: list[OmsOrderSummary] = []
        for raw in (data.get("oms_orders") or {}).values():
            if account_id and raw.get("account_id") != account_id:
                continue
            if status and raw.get("status") != status:
                continue
            out.append(OmsOrderSummary.model_validate(raw))
        return out

    def upsert_oms_order_version(self, version: Any) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("oms_order_versions", {})
            payload = (
                version.model_dump(mode="json")
                if hasattr(version, "model_dump")
                else dict(version)
            )
            key = f"{payload.get('order_id')}@{payload.get('version')}"
            data["oms_order_versions"][key] = payload
            self._write(data)

    def append_order_event(self, record: OmsOrderEventRecord) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("oms_order_events", {})
            data["oms_order_events"][record.event_id] = record.model_dump(mode="json")
            self._write(data)

    def list_order_events(self, order_id: str) -> list[OmsOrderEventRecord]:
        data = self._read()
        out: list[OmsOrderEventRecord] = []
        for raw in (data.get("oms_order_events") or {}).values():
            if raw.get("order_id") == order_id:
                out.append(OmsOrderEventRecord.model_validate(raw))
        out.sort(key=lambda e: e.created_at or "")
        return out

    def upsert_fill(self, record: OmsFillSummary) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("oms_fills", {})
            data["oms_fills"][record.fill_id] = record.model_dump(mode="json")
            self._write(data)

    def list_oms_fills(self, order_id: str) -> list[OmsFillSummary]:
        data = self._read()
        out: list[OmsFillSummary] = []
        for raw in (data.get("oms_fills") or {}).values():
            if raw.get("order_id") == order_id:
                out.append(OmsFillSummary.model_validate(raw))
        return out

    def enqueue_outbox(self, record: OmsOutboxRecord) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("oms_outbox", {})
            data["oms_outbox"][record.outbox_id] = record.model_dump(mode="json")
            self._write(data)

    def list_outbox(self, *, limit: int = 100) -> list[OmsOutboxRecord]:
        data = self._read()
        pending = [
            OmsOutboxRecord.model_validate(raw)
            for raw in (data.get("oms_outbox") or {}).values()
            if raw.get("status") == "PENDING"
        ]
        pending.sort(key=lambda r: r.created_at or "")
        return pending[:limit]

    def mark_outbox(self, outbox_id: str, status: str) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("oms_outbox", {})
            raw = data["oms_outbox"].get(outbox_id)
            if not raw:
                return
            raw["status"] = status
            if status == "SENT":
                raw["sent_at"] = _utc_now()
            data["oms_outbox"][outbox_id] = raw
            self._write(data)

    def upsert_cancel_request(self, request: Any) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("oms_cancel_requests", {})
            payload = (
                request.model_dump(mode="json")
                if hasattr(request, "model_dump")
                else dict(request)
            )
            data["oms_cancel_requests"][payload.get("request_id")] = payload
            self._write(data)

    def upsert_replace_request(self, request: Any) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("oms_replace_requests", {})
            payload = (
                request.model_dump(mode="json")
                if hasattr(request, "model_dump")
                else dict(request)
            )
            data["oms_replace_requests"][payload.get("request_id")] = payload
            self._write(data)

    def upsert_broker_session(self, record: BrokerSessionSummary) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("broker_sessions", {})
            data["broker_sessions"][record.session_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def upsert_broker_order_link(self, record: BrokerOrderLinkRecord) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("broker_order_links", {})
            data.setdefault("broker_order_links_by_client", {})
            data.setdefault("broker_order_links_by_broker", {})
            payload = record.model_dump(mode="json")
            data["broker_order_links"][record.order_id] = payload
            data["broker_order_links_by_client"][
                record.client_order_id
            ] = record.order_id
            if record.broker_order_id:
                data["broker_order_links_by_broker"][
                    f"{record.broker_id}|{record.broker_order_id}"
                ] = record.order_id
            self._write(data)

    def get_order_link_by_client_id(
        self, client_order_id: str
    ) -> BrokerOrderLinkRecord:
        data = self._read()
        oid = (data.get("broker_order_links_by_client") or {}).get(client_order_id)
        if not oid:
            raise KeyError(f"broker link client not found: {client_order_id!r}")
        raw = (data.get("broker_order_links") or {}).get(oid)
        if not raw:
            raise KeyError(f"broker link not found: {oid!r}")
        return BrokerOrderLinkRecord.model_validate(raw)

    def get_order_link_by_broker_id(
        self, broker_id: str, broker_order_id: str
    ) -> BrokerOrderLinkRecord:
        data = self._read()
        oid = (data.get("broker_order_links_by_broker") or {}).get(
            f"{broker_id}|{broker_order_id}"
        )
        if not oid:
            raise KeyError(
                f"broker link not found: {broker_id!r}/{broker_order_id!r}"
            )
        raw = (data.get("broker_order_links") or {}).get(oid)
        if not raw:
            raise KeyError(f"broker link not found: {oid!r}")
        return BrokerOrderLinkRecord.model_validate(raw)

    def try_record_execution_dedup(
        self, broker_id: str, broker_execution_id: str
    ) -> bool:
        """首次写入返回 True；已存在返回 False。"""
        with self._lock:
            data = self._read()
            data.setdefault("broker_execution_dedup", {})
            key = f"{broker_id}|{broker_execution_id}"
            if key in data["broker_execution_dedup"]:
                return False
            data["broker_execution_dedup"][key] = {
                "broker_id": broker_id,
                "broker_execution_id": broker_execution_id,
                "created_at": _utc_now(),
            }
            self._write(data)
            return True

    def append_broker_event_index(
        self, record: BrokerEventIndexRecord
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("broker_event_index", {})
            data["broker_event_index"][record.event_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def upsert_reconciliation_run(
        self, record: ReconciliationRunSummary
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("reconciliation_runs", {})
            data["reconciliation_runs"][record.run_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def upsert_reconciliation_finding(
        self, record: ReconciliationFindingSummary
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("reconciliation_findings", {})
            data["reconciliation_findings"][record.finding_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def list_reconciliation_findings(
        self,
        *,
        run_id: str = "",
        account_id: str = "",
        status: str = "",
    ) -> list[ReconciliationFindingSummary]:
        data = self._read()
        rows = list((data.get("reconciliation_findings") or {}).values())
        out: list[ReconciliationFindingSummary] = []
        for raw in rows:
            if run_id and str(raw.get("run_id") or "") != run_id:
                continue
            if status and str(raw.get("status") or "") != status:
                continue
            if account_id:
                meta = raw.get("metadata") or {}
                if str(meta.get("account_id") or "") != account_id:
                    # 也允许经 run 反查
                    runs = data.get("reconciliation_runs") or {}
                    run = runs.get(str(raw.get("run_id") or ""))
                    if not run or str(run.get("account_id") or "") != account_id:
                        continue
            out.append(ReconciliationFindingSummary.model_validate(raw))
        return out

    def append_broker_snapshot_index(
        self, record: BrokerSnapshotIndexRecord
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("broker_snapshot_index", {})
            data["broker_snapshot_index"][record.snapshot_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_reconciliation_cursor(
        self,
        account_id: str,
        *,
        broker_id: str = "",
        cursor_type: str = "EXECUTION",
    ) -> ReconciliationCursorRecord:
        data = self._read()
        key = f"{account_id}|{broker_id}|{cursor_type}"
        raw = (data.get("reconciliation_cursors") or {}).get(key)
        if not raw:
            raise KeyError(f"cursor not found: {key!r}")
        return ReconciliationCursorRecord.model_validate(raw)

    def set_reconciliation_cursor(
        self, record: ReconciliationCursorRecord
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("reconciliation_cursors", {})
            key = f"{record.account_id}|{record.broker_id}|{record.cursor_type}"
            data["reconciliation_cursors"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_reconciliation_gate(
        self, account_id: str
    ) -> ReconciliationGateRecord:
        data = self._read()
        raw = (data.get("reconciliation_gates") or {}).get(account_id)
        if not raw:
            raise KeyError(f"gate not found: {account_id!r}")
        return ReconciliationGateRecord.model_validate(raw)

    def set_reconciliation_gate(
        self, record: ReconciliationGateRecord
    ) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("reconciliation_gates", {})
            data["reconciliation_gates"][record.account_id] = record.model_dump(
                mode="json"
            )
            self._write(data)


class D1ResearchRegistry:
    """经 Worker 写入 qd_research。"""

    def upsert_data_version(
        self,
        *,
        dataset_code: str,
        version: str,
        schema_version: str,
        status: str,
        checksum: str,
        r2_uri: str,
        row_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        d1_client.query(
            """
            INSERT INTO data_version (
              dataset_code, version, schema_version, status, row_count,
              checksum, r2_uri, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dataset_code, version) DO UPDATE SET
              schema_version=excluded.schema_version,
              status=excluded.status,
              row_count=excluded.row_count,
              checksum=excluded.checksum,
              r2_uri=excluded.r2_uri,
              metadata_json=excluded.metadata_json
            """,
            [
                dataset_code,
                version,
                schema_version,
                status,
                row_count,
                checksum,
                r2_uri,
                json.dumps(metadata or {}, ensure_ascii=False),
                _utc_now(),
            ],
        )
        rows = d1_client.query(
            "SELECT data_version_id FROM data_version WHERE dataset_code=? AND version=?",
            [dataset_code, version],
        )
        return int(rows[0]["data_version_id"])

    def create_snapshot(
        self,
        *,
        snapshot_id: str,
        name: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        d1_client.query(
            """
            INSERT INTO data_snapshot (snapshot_id, name, created_at, metadata_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
              name=excluded.name,
              metadata_json=excluded.metadata_json
            """,
            [snapshot_id, name, _utc_now(), json.dumps(metadata or {}, ensure_ascii=False)],
        )
        for item in items:
            dv_id = item.get("data_version_id")
            if dv_id is None:
                raise ValueError("snapshot item requires data_version_id for D1 registry")
            d1_client.query(
                """
                INSERT INTO data_snapshot_item (snapshot_id, data_version_id, path, checksum)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_id, data_version_id) DO UPDATE SET
                  path=excluded.path,
                  checksum=excluded.checksum
                """,
                [snapshot_id, int(dv_id), item.get("path") or "", item.get("checksum")],
            )
        return snapshot_id

    def upsert_dataset(
        self, definition: DatasetDefinition, *, status: str = "ACTIVE"
    ) -> None:
        """登记 Dataset；status 文本列可写 validated（不改 DDL）。"""
        d1_client.query(
            """
            INSERT INTO dataset (
              code, version, name, frequency, universe_code, universe_version,
              snapshot_id, schema_version, definition_json, price_policy_json,
              status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, version) DO UPDATE SET
              name=excluded.name,
              frequency=excluded.frequency,
              universe_code=excluded.universe_code,
              universe_version=excluded.universe_version,
              snapshot_id=excluded.snapshot_id,
              schema_version=excluded.schema_version,
              definition_json=excluded.definition_json,
              price_policy_json=excluded.price_policy_json,
              status=excluded.status
            """,
            [
                definition.code,
                definition.version,
                definition.name,
                definition.frequency,
                definition.universe_code,
                definition.universe_version,
                definition.snapshot_id,
                definition.schema_version,
                json.dumps(definition.model_dump(mode="json"), ensure_ascii=False),
                json.dumps(definition.price_policy.model_dump(mode="json"), ensure_ascii=False),
                status,
                _utc_now(),
            ],
        )

    def get_dataset(self, dataset_ref: str) -> DatasetHandle:
        code, version = _split_ref(dataset_ref)
        rows = d1_client.query(
            "SELECT * FROM dataset WHERE code=? AND version=?",
            [code, version],
        )
        if not rows:
            raise KeyError(f"dataset not found: {dataset_ref}")
        row = rows[0]
        definition = DatasetDefinition.model_validate(json.loads(row["definition_json"]))
        # 覆盖可能漂移的 registry 列
        definition = definition.model_copy(
            update={
                "code": row["code"],
                "version": row["version"],
                "snapshot_id": row.get("snapshot_id") or definition.snapshot_id,
                "price_policy": PricePolicy.model_validate(
                    json.loads(row.get("price_policy_json") or "{}")
                ),
            }
        )
        snapshot = self.get_snapshot(definition.snapshot_id)
        digest = compute_dataset_hash(
            dataset_definition=definition.model_dump(mode="json"),
            dataset_version=definition.version,
            snapshot_id=definition.snapshot_id,
            schema_version=definition.schema_version,
            processor_version=definition.processor or "",
            materializer_version="none",
            price_policy=definition.price_policy.model_dump(mode="json"),
        )
        return DatasetHandle(
            definition=definition,
            snapshot=snapshot,
            dataset_hash=digest,
            manifest_uri="",
        )

    def upsert_feature(self, feature: FeatureDefinition) -> None:
        """登记 Feature/Factor 到 D1；写 feature_dependency；同版本不可变。"""
        from app.services.research_data.factor_lab.dependencies import (
            format_dependency,
            parse_dependencies,
        )
        from app.services.research_data.factor_lab.hash import compute_factor_hash
        from app.services.research_data.factor_lab.immutability import (
            FeatureImmutabilityError as _FIE,
            assert_feature_immutable,
            ensure_factor_hash,
        )

        feat = ensure_factor_hash(feature)
        feat = feat.model_copy(update={"factor_hash": compute_factor_hash(feat)})
        existing_rows = d1_client.query(
            "SELECT * FROM feature WHERE code=? AND version=?",
            [feat.code, feat.version],
        )
        if existing_rows:
            old = self.get_feature(f"{feat.code}@{feat.version}")
            try:
                assert_feature_immutable(old, feat)
            except _FIE as exc:
                raise FeatureImmutabilityError(str(exc)) from exc
            return

        # definition_json 保留扩展字段快照（兼容旧列）
        def_blob = dict(feat.definition or {})
        def_blob.update(
            {
                "description": feat.description,
                "factor_type": feat.factor_type,
                "computation_engine": feat.computation_engine,
                "engine_version": feat.engine_version,
                "universe": feat.universe,
                "information_policy": feat.information_policy,
                "schema_version": feat.schema_version,
                "factor_hash": feat.factor_hash,
                "processor_ref": feat.processor_ref,
                "price_policy": (
                    feat.price_policy.model_dump(mode="json")
                    if feat.price_policy
                    else None
                ),
                "dependencies": list(feat.dependencies or []),
            }
        )
        d1_client.query(
            """
            INSERT INTO feature (
              code, version, name, expression, frequency, definition_json,
              backend, online_supported, status, created_at,
              description, factor_type, computation_engine, engine_version,
              universe, information_policy, schema_version, factor_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                feat.code,
                feat.version,
                feat.name,
                feat.expression,
                feat.frequency,
                json.dumps(def_blob, ensure_ascii=False),
                feat.backend,
                1 if feat.online_supported else 0,
                _utc_now(),
                feat.description or "",
                feat.factor_type,
                feat.computation_engine,
                feat.engine_version or "",
                feat.universe,
                feat.information_policy,
                feat.schema_version,
                feat.factor_hash,
            ],
        )
        rows = d1_client.query(
            "SELECT feature_id FROM feature WHERE code=? AND version=?",
            [feat.code, feat.version],
        )
        if not rows:
            return
        feature_id = rows[0]["feature_id"]
        d1_client.query(
            "DELETE FROM feature_dependency WHERE feature_id=?",
            [feature_id],
        )
        for dep in parse_dependencies(feat.dependencies or []):
            d1_client.query(
                """
                INSERT INTO feature_dependency
                  (feature_id, dependency_type, dependency_code)
                VALUES (?, ?, ?)
                """,
                [feature_id, dep.dependency_type, dep.dependency_code],
            )
            # 规范化字符串写入 definition 侧已由 parse 保证
            _ = format_dependency(dep)

    def get_feature(self, feature_ref: str) -> FeatureDefinition:
        code, version = _split_ref(feature_ref)
        rows = d1_client.query(
            "SELECT * FROM feature WHERE code=? AND version=?",
            [code, version],
        )
        if not rows:
            raise KeyError(f"feature not found: {feature_ref}")
        row = rows[0]
        blob = json.loads(row.get("definition_json") or "{}")
        dep_rows = d1_client.query(
            """
            SELECT dependency_type, dependency_code
            FROM feature_dependency
            WHERE feature_id=?
            """,
            [row["feature_id"]],
        )
        deps_from_table = [
            f"{r['dependency_type']}:{r['dependency_code']}" for r in (dep_rows or [])
        ]
        deps = deps_from_table or list(blob.get("dependencies") or [])
        pp = blob.get("price_policy")
        price_policy = PricePolicy.model_validate(pp) if pp else None
        return FeatureDefinition(
            code=row["code"],
            version=row["version"],
            name=row["name"],
            expression=row["expression"],
            frequency=row["frequency"],
            backend=row.get("backend") or "r2_factor",
            online_supported=bool(row.get("online_supported")),
            definition={
                k: v
                for k, v in blob.items()
                if k
                not in {
                    "description",
                    "factor_type",
                    "computation_engine",
                    "engine_version",
                    "universe",
                    "information_policy",
                    "schema_version",
                    "factor_hash",
                    "processor_ref",
                    "price_policy",
                    "dependencies",
                }
            },
            dependencies=deps,
            description=row.get("description") or blob.get("description") or "",
            factor_type=row.get("factor_type") or blob.get("factor_type") or "CUSTOM",
            computation_engine=row.get("computation_engine")
            or blob.get("computation_engine")
            or "quantdinger",
            engine_version=row.get("engine_version")
            or blob.get("engine_version")
            or "",
            universe=row.get("universe") or blob.get("universe"),
            information_policy=row.get("information_policy")
            or blob.get("information_policy")
            or "UNKNOWN",
            schema_version=row.get("schema_version")
            or blob.get("schema_version")
            or "factor_daily_long@1",
            factor_hash=row.get("factor_hash") or blob.get("factor_hash"),
            price_policy=price_policy,
            processor_ref=blob.get("processor_ref"),
        )

    def upsert_processor(self, processor: ProcessorDefinition) -> None:
        """登记 Processor 到 D1；同 code@version 禁止改 pipeline。"""
        rows = d1_client.query(
            "SELECT definition_json FROM processor WHERE code=? AND version=?",
            [processor.code, processor.version],
        )
        if rows:
            existing = json.loads(rows[0]["definition_json"] or "{}")
            _assert_processor_immutable(existing, processor)
            return
        d1_client.query(
            """
            INSERT INTO processor (code, version, definition_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                processor.code,
                processor.version,
                json.dumps(processor.model_dump(mode="json"), ensure_ascii=False),
                _utc_now(),
            ],
        )

    def get_processor(self, processor_ref: str) -> ProcessorDefinition:
        """从 D1 读取 Processor。"""
        code, version = _split_ref(processor_ref)
        rows = d1_client.query(
            "SELECT * FROM processor WHERE code=? AND version=?",
            [code, version],
        )
        if not rows:
            raise KeyError(f"processor not found: {processor_ref}")
        raw = json.loads(rows[0]["definition_json"])
        return ProcessorDefinition.model_validate(raw)

    def upsert_model(self, model: ModelDefinition) -> None:
        d1_client.query(
            """
            INSERT INTO model (code, name, engine, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) DO NOTHING
            """,
            [model.code, model.name, model.engine, _utc_now()],
        )

    def get_model(self, model_code: str) -> ModelDefinition:
        rows = d1_client.query("SELECT * FROM model WHERE code=?", [model_code])
        if not rows:
            raise KeyError(f"model not found: {model_code!r}")
        row = rows[0]
        return ModelDefinition(
            code=row["code"],
            version="1",
            name=row["name"],
            engine=row["engine"],
            config={},
        )

    def upsert_model_version(self, record: ModelVersionRecord) -> None:
        self.upsert_model(
            ModelDefinition(
                code=record.model_code,
                version=record.version,
                name=record.model_code,
                engine="lightgbm",
                config=record.config,
            )
        )
        rows = d1_client.query(
            """
            SELECT mv.model_version_id FROM model_version mv
            JOIN model m ON m.model_id = mv.model_id
            WHERE m.code=? AND mv.version=?
            """,
            [record.model_code, record.version],
        )
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
        if rows:
            d1_client.query(
                """
                UPDATE model_version SET config_json=?, artifact_id=?, metrics_json=?
                WHERE model_version_id=?
                """,
                [
                    payload,
                    record.artifact_id,
                    json.dumps(record.metrics or {}, ensure_ascii=False),
                    rows[0]["model_version_id"],
                ],
            )
            return
        model_rows = d1_client.query(
            "SELECT model_id FROM model WHERE code=?", [record.model_code]
        )
        d1_client.query(
            """
            INSERT INTO model_version (
              model_id, version, config_json, artifact_id, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                model_rows[0]["model_id"],
                record.version,
                payload,
                record.artifact_id,
                json.dumps(record.metrics or {}, ensure_ascii=False),
                _utc_now(),
            ],
        )

    def get_model_version(self, model_version_ref: str) -> ModelVersionRecord:
        code, version = _split_ref(model_version_ref)
        rows = d1_client.query(
            """
            SELECT mv.config_json FROM model_version mv
            JOIN model m ON m.model_id = mv.model_id
            WHERE m.code=? AND mv.version=?
            """,
            [code, version],
        )
        if not rows:
            raise KeyError(f"model_version not found: {model_version_ref}")
        return ModelVersionRecord.model_validate(json.loads(rows[0]["config_json"]))

    def upsert_artifact(self, record: ArtifactRecord) -> None:
        d1_client.query(
            """
            INSERT INTO artifact (
              artifact_id, artifact_type, storage_uri, checksum, size_bytes,
              metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
              storage_uri=excluded.storage_uri,
              checksum=excluded.checksum,
              size_bytes=excluded.size_bytes,
              metadata_json=excluded.metadata_json
            """,
            [
                record.artifact_id,
                record.artifact_type,
                record.storage_uri,
                record.checksum,
                record.size_bytes,
                json.dumps(record.metadata or {}, ensure_ascii=False),
                _utc_now(),
            ],
        )

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        rows = d1_client.query(
            "SELECT * FROM artifact WHERE artifact_id=?", [artifact_id]
        )
        if not rows:
            raise KeyError(f"artifact not found: {artifact_id!r}")
        row = rows[0]
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            artifact_type=row["artifact_type"],
            storage_uri=row["storage_uri"],
            checksum=row.get("checksum"),
            size_bytes=row.get("size_bytes"),
            metadata=json.loads(row.get("metadata_json") or "{}"),
        )

    def upsert_experiment(self, experiment: ExperimentDefinition) -> None:
        """写入 D1 experiment；扩展字段塞进 parameters_json 以便回填。"""
        params = dict(experiment.parameters or {})
        params.update(
            {
                "dataset_ref": experiment.dataset_ref,
                "model_version_ref": experiment.model_version_ref,
                "processor_ref": experiment.processor_ref,
                "strategy_version": experiment.strategy_version,
                "manifest_uri": experiment.manifest_uri,
                "repro_fingerprint": experiment.repro_fingerprint,
                "bundle_hash": experiment.bundle_hash,
                "prediction_fingerprint": experiment.prediction_fingerprint,
                "model_artifact_id": experiment.model_artifact_id,
                "signal_artifact_id": experiment.signal_artifact_id,
                "signal_run_id": experiment.signal_run_id,
                "feature_refs": experiment.feature_refs,
                "segments": experiment.segments,
                "status": experiment.status,
            }
        )
        d1_client.query(
            """
            INSERT INTO experiment (
              experiment_id, name, snapshot_id, dataset_hash, status,
              mlflow_run_id, parameters_json, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(experiment_id) DO UPDATE SET
              metrics_json=excluded.metrics_json,
              mlflow_run_id=excluded.mlflow_run_id,
              parameters_json=excluded.parameters_json,
              status=excluded.status
            """,
            [
                experiment.experiment_id,
                experiment.name,
                experiment.snapshot_id,
                experiment.dataset_hash,
                experiment.status or "COMPLETED",
                experiment.mlflow_run_id,
                json.dumps(params, ensure_ascii=False),
                json.dumps(experiment.metrics or {}, ensure_ascii=False),
                _utc_now(),
            ],
        )

    def get_experiment(self, experiment_id: str) -> ExperimentDefinition:
        rows = d1_client.query(
            "SELECT * FROM experiment WHERE experiment_id=?", [experiment_id]
        )
        if not rows:
            raise KeyError(f"experiment not found: {experiment_id!r}")
        row = rows[0]
        params = json.loads(row.get("parameters_json") or "{}")
        metrics = json.loads(row.get("metrics_json") or "{}")
        return ExperimentDefinition(
            experiment_id=row["experiment_id"],
            name=row["name"],
            dataset_ref=str(params.get("dataset_ref") or row.get("dataset_ref") or ""),
            snapshot_id=row.get("snapshot_id") or "",
            dataset_hash=row.get("dataset_hash") or "",
            model_version_ref=params.get("model_version_ref"),
            mlflow_run_id=row.get("mlflow_run_id"),
            parameters=params,
            feature_refs=list(params.get("feature_refs") or []),
            processor_ref=params.get("processor_ref"),
            strategy_version=params.get("strategy_version"),
            model_artifact_id=params.get("model_artifact_id"),
            signal_artifact_id=params.get("signal_artifact_id"),
            signal_run_id=params.get("signal_run_id"),
            bundle_hash=params.get("bundle_hash"),
            prediction_fingerprint=params.get("prediction_fingerprint"),
            repro_fingerprint=params.get("repro_fingerprint"),
            metrics=metrics if isinstance(metrics, dict) else {},
            manifest_uri=str(params.get("manifest_uri") or ""),
            status=row.get("status") or params.get("status") or "COMPLETED",
            segments=dict(params.get("segments") or {}),
        )

    def upsert_signal_run(self, record: SignalRunRecord) -> None:
        """D1 无独立 signal_run 表；Phase 2E 索引仅 Local JSON，远端依赖 signal artifact。

        pipeline 已调用 upsert_artifact(type=signal)；此处不重复写入以免覆盖类型。
        """
        _ = record
        return

    def get_signal_run(self, signal_run_id: str) -> SignalRunRecord:
        """从 signal artifact 元数据重建（D1 无独立表）。"""
        art = self.get_artifact(signal_run_id)
        meta = dict(art.metadata or {})
        return SignalRunRecord(
            signal_run_id=signal_run_id,
            strategy_version=str(meta.get("strategy_version") or ""),
            prediction_fingerprint=str(meta.get("prediction_fingerprint") or ""),
            artifact_id=str(meta.get("artifact_id") or art.artifact_id),
            storage_uri=art.storage_uri,
            cash_weight=float(meta.get("cash_weight") or 0.0),
            metadata=meta,
        )

    def upsert_consistency_run(self, record: ConsistencyRunRecord) -> None:
        """D1 无独立表：索引落在 consistency artifact metadata（由 artifact_store 写入）。"""
        _ = record
        return

    def get_consistency_run(self, run_id: str) -> ConsistencyRunRecord:
        """从 consistency artifact 元数据重建。"""
        art = self.get_artifact(run_id)
        meta = dict(art.metadata or {})
        return ConsistencyRunRecord(
            run_id=run_id,
            dataset_hash=str(meta.get("dataset_hash") or ""),
            qlib_result_id=meta.get("qlib_result_id"),
            qd_result_id=meta.get("qd_result_id"),
            status=meta.get("status") or "PASSED",
            max_equity_diff=(
                float(meta["max_equity_diff"])
                if meta.get("max_equity_diff") is not None
                else None
            ),
            max_position_diff=(
                float(meta["max_position_diff"])
                if meta.get("max_position_diff") is not None
                else None
            ),
            artifact_uri=art.storage_uri,
            level=str(meta.get("level") or ""),
            semantic_fingerprint=meta.get("semantic_fingerprint"),
            created_at=meta.get("created_at"),
            metadata=meta,
        )

    def upsert_factor_dataset(self, record: FactorDatasetRecord) -> None:
        """D1：优先写 factor_dataset 表；失败则依赖 artifact metadata。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_dataset (
                  factor_dataset_id, factor_ref, factor_hash, dataset_hash,
                  snapshot_id, universe_code, frequency, start_date, end_date,
                  storage_uri, checksum, row_count, layout, schema_version,
                  status, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(factor_dataset_id) DO UPDATE SET
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  row_count=excluded.row_count,
                  status=excluded.status,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.factor_dataset_id,
                    record.factor_ref,
                    record.factor_hash,
                    record.dataset_hash,
                    record.snapshot_id,
                    record.universe_code,
                    record.frequency,
                    record.start_date,
                    record.end_date,
                    record.storage_uri,
                    record.checksum,
                    record.row_count,
                    record.layout,
                    record.schema_version,
                    record.status,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            # 未跑 migration 时：仅靠 upsert_artifact(type=factor_dataset)
            return

    def get_factor_dataset(self, factor_dataset_id: str) -> FactorDatasetRecord:
        """从 factor_dataset 表或 artifact 元数据读取。"""
        try:
            rows = d1_client.query(
                "SELECT * FROM factor_dataset WHERE factor_dataset_id=?",
                [factor_dataset_id],
            )
        except Exception:
            rows = []
        if rows:
            row = rows[0]
            meta = json.loads(row.get("metadata_json") or "{}")
            return FactorDatasetRecord(
                factor_dataset_id=row["factor_dataset_id"],
                factor_ref=row["factor_ref"],
                factor_hash=row["factor_hash"],
                dataset_hash=row["dataset_hash"],
                snapshot_id=row["snapshot_id"],
                universe_code=row.get("universe_code") or "",
                frequency=row.get("frequency") or "1d",
                start_date=row.get("start_date") or "",
                end_date=row.get("end_date") or "",
                storage_uri=row.get("storage_uri") or "",
                checksum=row.get("checksum"),
                row_count=row.get("row_count"),
                layout=row.get("layout") or "long",
                schema_version=row.get("schema_version") or "factor_daily_long@1",
                status=row.get("status") or "ACTIVE",
                created_at=row.get("created_at"),
                metadata=meta if isinstance(meta, dict) else {},
            )
        art = self.get_artifact(factor_dataset_id)
        meta = dict(art.metadata or {})
        return FactorDatasetRecord(
            factor_dataset_id=factor_dataset_id,
            factor_ref=str(meta.get("factor_ref") or ""),
            factor_hash=str(meta.get("factor_hash") or ""),
            dataset_hash=str(meta.get("dataset_hash") or ""),
            snapshot_id=str(meta.get("snapshot_id") or ""),
            universe_code=str(meta.get("universe_code") or ""),
            storage_uri=art.storage_uri,
            checksum=art.checksum,
            layout=meta.get("layout") or "long",
            schema_version=str(meta.get("schema_version") or "factor_daily_long@1"),
            metadata=meta,
        )

    def upsert_evaluation_dataset(self, record: EvaluationDatasetRecord) -> None:
        """D1：写 evaluation_dataset 表；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO evaluation_dataset (
                  evaluation_hash, factor_dataset_id, factor_dataset_hash,
                  snapshot_id, universe_code, universe_version,
                  start_date, end_date, return_spec_json, price_policy_json,
                  evaluator_version, mode, storage_uri, checksum, row_count,
                  schema_version, status, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evaluation_hash) DO UPDATE SET
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  row_count=excluded.row_count,
                  status=excluded.status,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.evaluation_hash,
                    record.factor_dataset_id,
                    record.factor_dataset_hash,
                    record.snapshot_id,
                    record.universe_code,
                    record.universe_version,
                    record.start_date,
                    record.end_date,
                    json.dumps(record.return_spec or {}, ensure_ascii=False),
                    json.dumps(
                        record.price_policy.model_dump(mode="json")
                        if record.price_policy
                        else {},
                        ensure_ascii=False,
                    ),
                    record.evaluator_version,
                    record.mode,
                    record.storage_uri,
                    record.checksum,
                    record.row_count,
                    record.schema_version,
                    record.status,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_evaluation_dataset(self, evaluation_hash: str) -> EvaluationDatasetRecord:
        """从 evaluation_dataset 表或 artifact 元数据读取。"""
        try:
            rows = d1_client.query(
                "SELECT * FROM evaluation_dataset WHERE evaluation_hash=?",
                [evaluation_hash],
            )
        except Exception:
            rows = []
        if rows:
            row = rows[0]
            meta = json.loads(row.get("metadata_json") or "{}")
            pp_raw = json.loads(row.get("price_policy_json") or "{}")
            return EvaluationDatasetRecord(
                evaluation_hash=row["evaluation_hash"],
                factor_dataset_id=row["factor_dataset_id"],
                factor_dataset_hash=row["factor_dataset_hash"],
                snapshot_id=row["snapshot_id"],
                universe_code=row.get("universe_code") or "",
                universe_version=row.get("universe_version") or "",
                start_date=row.get("start_date") or "",
                end_date=row.get("end_date") or "",
                return_spec=json.loads(row.get("return_spec_json") or "{}"),
                price_policy=PricePolicy.model_validate(pp_raw) if pp_raw else None,
                evaluator_version=row.get("evaluator_version") or "qd_factor_eval@1",
                mode=row.get("mode") or "CROSS_SECTIONAL",
                storage_uri=row.get("storage_uri") or "",
                checksum=row.get("checksum"),
                row_count=row.get("row_count"),
                schema_version=row.get("schema_version") or "evaluation_panel@1",
                status=row.get("status") or "ACTIVE",
                created_at=row.get("created_at"),
                metadata=meta if isinstance(meta, dict) else {},
            )
        art = self.get_artifact(evaluation_hash)
        meta = dict(art.metadata or {})
        return EvaluationDatasetRecord(
            evaluation_hash=evaluation_hash,
            factor_dataset_id=str(meta.get("factor_dataset_id") or ""),
            factor_dataset_hash=str(meta.get("factor_dataset_hash") or ""),
            snapshot_id=str(meta.get("snapshot_id") or ""),
            universe_code=str(meta.get("universe_code") or ""),
            storage_uri=art.storage_uri,
            checksum=art.checksum,
            schema_version=str(meta.get("schema_version") or "evaluation_panel@1"),
            metadata=meta,
        )

    def upsert_factor_evaluation_summary(
        self, record: FactorEvaluationSummary
    ) -> None:
        """D1：写 factor_evaluation_summary；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_evaluation_summary (
                  metric_hash, horizon, evaluation_hash, factor_dataset_id,
                  mean_ic, median_ic, std_ic, min_ic, max_ic, ic_ir, ic_t_stat,
                  positive_ic_ratio, mean_rank_ic, median_rank_ic, std_rank_ic,
                  min_rank_ic, max_rank_ic, rank_ic_ir, rank_ic_t_stat,
                  positive_rank_ic_ratio, valid_day_count, total_day_count,
                  direction, metric_version, storage_uri, checksum,
                  created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(metric_hash, horizon) DO UPDATE SET
                  mean_ic=excluded.mean_ic,
                  mean_rank_ic=excluded.mean_rank_ic,
                  ic_ir=excluded.ic_ir,
                  rank_ic_ir=excluded.rank_ic_ir,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.metric_hash,
                    int(record.horizon),
                    record.evaluation_hash,
                    record.factor_dataset_id,
                    record.mean_ic,
                    record.median_ic,
                    record.std_ic,
                    record.min_ic,
                    record.max_ic,
                    record.ic_ir,
                    record.ic_t_stat,
                    record.positive_ic_ratio,
                    record.mean_rank_ic,
                    record.median_rank_ic,
                    record.std_rank_ic,
                    record.min_rank_ic,
                    record.max_rank_ic,
                    record.rank_ic_ir,
                    record.rank_ic_t_stat,
                    record.positive_rank_ic_ratio,
                    record.valid_day_count,
                    record.total_day_count,
                    record.direction,
                    record.metric_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_evaluation_summary(
        self, metric_hash: str, horizon: int
    ) -> FactorEvaluationSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_evaluation_summary
                WHERE metric_hash=? AND horizon=?
                """,
                [metric_hash, int(horizon)],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"factor_evaluation_summary not found: {metric_hash!r} h={horizon}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return FactorEvaluationSummary(
            metric_hash=row["metric_hash"],
            evaluation_hash=row["evaluation_hash"],
            factor_dataset_id=row.get("factor_dataset_id") or "",
            horizon=int(row["horizon"]),
            mean_ic=row.get("mean_ic"),
            median_ic=row.get("median_ic"),
            std_ic=row.get("std_ic"),
            min_ic=row.get("min_ic"),
            max_ic=row.get("max_ic"),
            ic_ir=row.get("ic_ir"),
            ic_t_stat=row.get("ic_t_stat"),
            positive_ic_ratio=row.get("positive_ic_ratio"),
            mean_rank_ic=row.get("mean_rank_ic"),
            median_rank_ic=row.get("median_rank_ic"),
            std_rank_ic=row.get("std_rank_ic"),
            min_rank_ic=row.get("min_rank_ic"),
            max_rank_ic=row.get("max_rank_ic"),
            rank_ic_ir=row.get("rank_ic_ir"),
            rank_ic_t_stat=row.get("rank_ic_t_stat"),
            positive_rank_ic_ratio=row.get("positive_rank_ic_ratio"),
            valid_day_count=int(row.get("valid_day_count") or 0),
            total_day_count=int(row.get("total_day_count") or 0),
            direction=row.get("direction") or "AUTO",
            metric_version=row.get("metric_version") or "qd_factor_metrics@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_factor_group_evaluation(
        self, record: GroupEvaluationSummary
    ) -> None:
        """D1：写 factor_group_evaluation；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_group_evaluation (
                  group_evaluation_hash, horizon, evaluation_hash, factor_dataset_id,
                  group_count, weighting_method, direction, portfolio_mode,
                  long_group, short_group,
                  mean_long_return, mean_short_return, mean_long_short_return,
                  mean_turnover, mean_estimated_cost, mean_net_long_short_return,
                  valid_day_count, total_day_count, group_version,
                  storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(group_evaluation_hash, horizon) DO UPDATE SET
                  mean_long_short_return=excluded.mean_long_short_return,
                  mean_turnover=excluded.mean_turnover,
                  mean_net_long_short_return=excluded.mean_net_long_short_return,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.group_evaluation_hash,
                    int(record.horizon),
                    record.evaluation_hash,
                    record.factor_dataset_id,
                    int(record.group_count),
                    record.weighting_method,
                    record.direction,
                    record.portfolio_mode,
                    int(record.long_group),
                    int(record.short_group),
                    record.mean_long_return,
                    record.mean_short_return,
                    record.mean_long_short_return,
                    record.mean_turnover,
                    record.mean_estimated_cost,
                    record.mean_net_long_short_return,
                    record.valid_day_count,
                    record.total_day_count,
                    record.group_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_group_evaluation(
        self, group_evaluation_hash: str, horizon: int
    ) -> GroupEvaluationSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_group_evaluation
                WHERE group_evaluation_hash=? AND horizon=?
                """,
                [group_evaluation_hash, int(horizon)],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"factor_group_evaluation not found: {group_evaluation_hash!r} h={horizon}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return GroupEvaluationSummary(
            group_evaluation_hash=row["group_evaluation_hash"],
            evaluation_hash=row["evaluation_hash"],
            factor_dataset_id=row.get("factor_dataset_id") or "",
            horizon=int(row["horizon"]),
            group_count=int(row.get("group_count") or 10),
            weighting_method=row.get("weighting_method") or "EQUAL_WEIGHT",
            direction=row.get("direction") or "POSITIVE",
            portfolio_mode=row.get("portfolio_mode") or "BOTH",
            long_group=int(row.get("long_group") or 1),
            short_group=int(row.get("short_group") or 10),
            mean_long_return=row.get("mean_long_return"),
            mean_short_return=row.get("mean_short_return"),
            mean_long_short_return=row.get("mean_long_short_return"),
            mean_turnover=row.get("mean_turnover"),
            mean_estimated_cost=row.get("mean_estimated_cost"),
            mean_net_long_short_return=row.get("mean_net_long_short_return"),
            valid_day_count=int(row.get("valid_day_count") or 0),
            total_day_count=int(row.get("total_day_count") or 0),
            group_version=row.get("group_version") or "qd_factor_groups@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_factor_stability_evaluation(
        self, record: FactorStabilitySummary
    ) -> None:
        """D1：写 factor_stability_evaluation；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_stability_evaluation (
                  stability_hash, horizon, evaluation_hash, factor_dataset_id,
                  rolling_windows_json, decay_summary_json, regime_summary_json,
                  ic_stability_metrics_json, group_stability_metrics_json,
                  stability_version, storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(stability_hash, horizon) DO UPDATE SET
                  decay_summary_json=excluded.decay_summary_json,
                  regime_summary_json=excluded.regime_summary_json,
                  ic_stability_metrics_json=excluded.ic_stability_metrics_json,
                  group_stability_metrics_json=excluded.group_stability_metrics_json,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.stability_hash,
                    int(record.horizon),
                    record.evaluation_hash,
                    record.factor_dataset_id,
                    json.dumps(record.rolling_windows_json or [], ensure_ascii=False),
                    json.dumps(record.decay_summary_json or [], ensure_ascii=False),
                    json.dumps(record.regime_summary_json or [], ensure_ascii=False),
                    json.dumps(
                        record.ic_stability_metrics_json or {}, ensure_ascii=False
                    ),
                    json.dumps(
                        record.group_stability_metrics_json or {}, ensure_ascii=False
                    ),
                    record.stability_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_stability_evaluation(
        self, stability_hash: str, horizon: int
    ) -> FactorStabilitySummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_stability_evaluation
                WHERE stability_hash=? AND horizon=?
                """,
                [stability_hash, int(horizon)],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"factor_stability_evaluation not found: {stability_hash!r} h={horizon}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return FactorStabilitySummary(
            stability_hash=row["stability_hash"],
            evaluation_hash=row["evaluation_hash"],
            factor_dataset_id=row.get("factor_dataset_id") or "",
            horizon=int(row["horizon"]),
            rolling_windows_json=_loads("rolling_windows_json", []),
            decay_summary_json=_loads("decay_summary_json", []),
            regime_summary_json=_loads("regime_summary_json", []),
            ic_stability_metrics_json=_loads("ic_stability_metrics_json", {}),
            group_stability_metrics_json=_loads("group_stability_metrics_json", {}),
            stability_version=row.get("stability_version") or "qd_factor_stability@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_factor_neutralization(
        self, record: FactorNeutralizationSummary
    ) -> None:
        """D1：写 factor_neutralization；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_neutralization (
                  neutralization_hash, factor_dataset_id, factor_dataset_hash,
                  method, targets_json, r_squared_mean, diagnostics_json,
                  neutralized_factor_dataset_id, neutralization_version,
                  storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(neutralization_hash) DO UPDATE SET
                  r_squared_mean=excluded.r_squared_mean,
                  diagnostics_json=excluded.diagnostics_json,
                  neutralized_factor_dataset_id=excluded.neutralized_factor_dataset_id,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.neutralization_hash,
                    record.factor_dataset_id,
                    record.factor_dataset_hash,
                    record.method,
                    json.dumps(record.targets_json or [], ensure_ascii=False),
                    record.r_squared_mean,
                    json.dumps(record.diagnostics_json or {}, ensure_ascii=False),
                    record.neutralized_factor_dataset_id,
                    record.neutralization_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_neutralization(
        self, neutralization_hash: str
    ) -> FactorNeutralizationSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_neutralization
                WHERE neutralization_hash=?
                """,
                [neutralization_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"factor_neutralization not found: {neutralization_hash!r}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return FactorNeutralizationSummary(
            neutralization_hash=row["neutralization_hash"],
            factor_dataset_id=row["factor_dataset_id"],
            factor_dataset_hash=row.get("factor_dataset_hash") or "",
            method=row.get("method") or "REGRESSION",
            targets_json=_loads("targets_json", []),
            r_squared_mean=row.get("r_squared_mean"),
            diagnostics_json=_loads("diagnostics_json", {}),
            neutralized_factor_dataset_id=row.get("neutralized_factor_dataset_id")
            or "",
            neutralization_version=row.get("neutralization_version")
            or "qd_factor_neutralization@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_factor_combination(
        self, record: FactorCombinationSummary
    ) -> None:
        """D1：写 factor_combination；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_combination (
                  combination_hash, member_factor_dataset_ids_json, normalize,
                  weight_method, weights_json, correlation_summary_json,
                  redundancy_pairs_json, composite_factor_dataset_id,
                  combination_version, storage_uri, checksum, created_at,
                  metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(combination_hash) DO UPDATE SET
                  weights_json=excluded.weights_json,
                  correlation_summary_json=excluded.correlation_summary_json,
                  redundancy_pairs_json=excluded.redundancy_pairs_json,
                  composite_factor_dataset_id=excluded.composite_factor_dataset_id,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.combination_hash,
                    json.dumps(
                        record.member_factor_dataset_ids_json or [], ensure_ascii=False
                    ),
                    record.normalize,
                    record.weight_method,
                    json.dumps(record.weights_json or {}, ensure_ascii=False),
                    json.dumps(
                        record.correlation_summary_json or {}, ensure_ascii=False
                    ),
                    json.dumps(
                        record.redundancy_pairs_json or [], ensure_ascii=False
                    ),
                    record.composite_factor_dataset_id,
                    record.combination_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_combination(
        self, combination_hash: str
    ) -> FactorCombinationSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_combination
                WHERE combination_hash=?
                """,
                [combination_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"factor_combination not found: {combination_hash!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return FactorCombinationSummary(
            combination_hash=row["combination_hash"],
            member_factor_dataset_ids_json=_loads(
                "member_factor_dataset_ids_json", []
            ),
            normalize=row.get("normalize") or "RANK",
            weight_method=row.get("weight_method") or "EQUAL",
            weights_json=_loads("weights_json", {}),
            correlation_summary_json=_loads("correlation_summary_json", {}),
            redundancy_pairs_json=_loads("redundancy_pairs_json", []),
            composite_factor_dataset_id=row.get("composite_factor_dataset_id") or "",
            combination_version=row.get("combination_version")
            or "qd_factor_combination@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_factor_portfolio(self, record: FactorPortfolioSummary) -> None:
        """D1：写 factor_portfolio；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_portfolio (
                  portfolio_hash, factor_dataset_id, evaluation_hash,
                  construction_method, weight_method, rebalance_frequency,
                  selection_json, metrics_json, portfolio_version,
                  storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(portfolio_hash) DO UPDATE SET
                  selection_json=excluded.selection_json,
                  metrics_json=excluded.metrics_json,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.portfolio_hash,
                    record.factor_dataset_id,
                    record.evaluation_hash,
                    record.construction_method,
                    record.weight_method,
                    record.rebalance_frequency,
                    json.dumps(record.selection_json or {}, ensure_ascii=False),
                    json.dumps(record.metrics_json or {}, ensure_ascii=False),
                    record.portfolio_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_portfolio(self, portfolio_hash: str) -> FactorPortfolioSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_portfolio
                WHERE portfolio_hash=?
                """,
                [portfolio_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"factor_portfolio not found: {portfolio_hash!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return FactorPortfolioSummary(
            portfolio_hash=row["portfolio_hash"],
            factor_dataset_id=row["factor_dataset_id"],
            evaluation_hash=row.get("evaluation_hash") or "",
            construction_method=row.get("construction_method") or "LONG_ONLY",
            weight_method=row.get("weight_method") or "EQUAL_WEIGHT",
            rebalance_frequency=row.get("rebalance_frequency") or "DAILY",
            selection_json=_loads("selection_json", {}),
            metrics_json=_loads("metrics_json", {}),
            portfolio_version=row.get("portfolio_version")
            or "qd_factor_portfolio@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_research_strategy(self, record: ResearchStrategyRecord) -> None:
        """D1：写 research_strategy；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO research_strategy (
                  strategy_code, name, description, status, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_code) DO UPDATE SET
                  name=excluded.name,
                  description=excluded.description,
                  status=excluded.status,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.strategy_code,
                    record.name,
                    record.description,
                    record.status,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_research_strategy(self, strategy_code: str) -> ResearchStrategyRecord:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM research_strategy WHERE strategy_code=?
                """,
                [strategy_code],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"research_strategy not found: {strategy_code!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return ResearchStrategyRecord(
            strategy_code=row["strategy_code"],
            name=row.get("name") or "",
            description=row.get("description") or "",
            status=row.get("status") or "ACTIVE",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_strategy_research(self, record: StrategyResearchSummary) -> None:
        """D1：写 research_strategy_version；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO research_strategy_version (
                  strategy_hash, strategy_code, strategy_version_label,
                  factor_dataset_id, portfolio_hash, evaluation_hash,
                  signal_definition_json, rebalance_rule_json, holding_rule_json,
                  universe_code, snapshot_id, signal_row_count, position_row_count,
                  storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(strategy_hash) DO UPDATE SET
                  signal_row_count=excluded.signal_row_count,
                  position_row_count=excluded.position_row_count,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.strategy_hash,
                    record.strategy_code,
                    record.strategy_version_label,
                    record.factor_dataset_id,
                    record.portfolio_hash,
                    record.evaluation_hash,
                    json.dumps(
                        record.signal_definition_json or {}, ensure_ascii=False
                    ),
                    json.dumps(
                        record.rebalance_rule_json or {}, ensure_ascii=False
                    ),
                    json.dumps(record.holding_rule_json or {}, ensure_ascii=False),
                    record.universe_code,
                    record.snapshot_id,
                    int(record.signal_row_count),
                    int(record.position_row_count),
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_strategy_research(self, strategy_hash: str) -> StrategyResearchSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM research_strategy_version
                WHERE strategy_hash=?
                """,
                [strategy_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"strategy_research not found: {strategy_hash!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return StrategyResearchSummary(
            strategy_hash=row["strategy_hash"],
            strategy_code=row["strategy_code"],
            strategy_version_label=row.get("strategy_version_label")
            or "qd_strategy_research@1",
            factor_dataset_id=row.get("factor_dataset_id") or "",
            portfolio_hash=row.get("portfolio_hash") or "",
            evaluation_hash=row.get("evaluation_hash") or "",
            signal_definition_json=_loads("signal_definition_json", {}),
            rebalance_rule_json=_loads("rebalance_rule_json", {}),
            holding_rule_json=_loads("holding_rule_json", {}),
            universe_code=row.get("universe_code") or "",
            snapshot_id=row.get("snapshot_id") or "",
            signal_row_count=int(row.get("signal_row_count") or 0),
            position_row_count=int(row.get("position_row_count") or 0),
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_research_backtest(self, record: ResearchBacktestSummary) -> None:
        """D1：写 research_backtest_run；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO research_backtest_run (
                  backtest_hash, strategy_hash, start_date, end_date,
                  execution_policy, benchmark_mode, benchmark_instrument_key,
                  realism, market_rule, execution_profile_version,
                  metrics_json, benchmark_metrics_json, attribution_json,
                  engine_version, return_calculation_version,
                  storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(backtest_hash) DO UPDATE SET
                  realism=excluded.realism,
                  market_rule=excluded.market_rule,
                  execution_profile_version=excluded.execution_profile_version,
                  metrics_json=excluded.metrics_json,
                  benchmark_metrics_json=excluded.benchmark_metrics_json,
                  attribution_json=excluded.attribution_json,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.backtest_hash,
                    record.strategy_hash,
                    record.start_date,
                    record.end_date,
                    record.execution_policy,
                    record.benchmark_mode,
                    record.benchmark_instrument_key,
                    record.realism or "GROSS",
                    record.market_rule or "",
                    record.execution_profile_version
                    or "qd_research_execution@1",
                    json.dumps(record.metrics_json or {}, ensure_ascii=False),
                    json.dumps(
                        record.benchmark_metrics_json or {}, ensure_ascii=False
                    ),
                    json.dumps(record.attribution_json or {}, ensure_ascii=False),
                    record.engine_version,
                    record.return_calculation_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_research_backtest(self, backtest_hash: str) -> ResearchBacktestSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM research_backtest_run
                WHERE backtest_hash=?
                """,
                [backtest_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"research_backtest not found: {backtest_hash!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return ResearchBacktestSummary(
            backtest_hash=row["backtest_hash"],
            strategy_hash=row["strategy_hash"],
            start_date=row.get("start_date") or "",
            end_date=row.get("end_date") or "",
            execution_policy=row.get("execution_policy") or "NEXT_OPEN",
            benchmark_mode=row.get("benchmark_mode") or "NONE",
            benchmark_instrument_key=row.get("benchmark_instrument_key") or "",
            realism=row.get("realism") or "GROSS",
            market_rule=row.get("market_rule") or "",
            execution_profile_version=row.get("execution_profile_version")
            or "qd_research_execution@1",
            metrics_json=_loads("metrics_json", {}),
            benchmark_metrics_json=_loads("benchmark_metrics_json", {}),
            attribution_json=_loads("attribution_json", {}),
            engine_version=row.get("engine_version") or "qd_research_backtest@1",
            return_calculation_version=row.get("return_calculation_version")
            or "research_nav@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_research_qlib_run(self, record: QlibRunSummary) -> None:
        """D1：写 research_qlib_run；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO research_qlib_run (
                  qlib_run_hash, strategy_hash, start_date, end_date,
                  execution_policy, realism, market_rule,
                  dataset_ref, dataset_hash, materialization_id, backtest_hash,
                  compatibility_json, metrics_json,
                  engine_version, recorder_id,
                  storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(qlib_run_hash) DO UPDATE SET
                  compatibility_json=excluded.compatibility_json,
                  metrics_json=excluded.metrics_json,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.qlib_run_hash,
                    record.strategy_hash,
                    record.start_date,
                    record.end_date,
                    record.execution_policy,
                    record.realism,
                    record.market_rule,
                    record.dataset_ref,
                    record.dataset_hash,
                    record.materialization_id,
                    record.backtest_hash,
                    json.dumps(
                        record.compatibility_json or {}, ensure_ascii=False
                    ),
                    json.dumps(record.metrics_json or {}, ensure_ascii=False),
                    record.engine_version,
                    record.recorder_id,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_research_qlib_run(self, qlib_run_hash: str) -> QlibRunSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM research_qlib_run
                WHERE qlib_run_hash=?
                """,
                [qlib_run_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"research_qlib_run not found: {qlib_run_hash!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return QlibRunSummary(
            qlib_run_hash=row["qlib_run_hash"],
            strategy_hash=row["strategy_hash"],
            start_date=row.get("start_date") or "",
            end_date=row.get("end_date") or "",
            execution_policy=row.get("execution_policy") or "NEXT_OPEN",
            realism=row.get("realism") or "GROSS",
            market_rule=row.get("market_rule") or "",
            dataset_ref=row.get("dataset_ref") or "",
            dataset_hash=row.get("dataset_hash") or "",
            materialization_id=row.get("materialization_id") or "",
            backtest_hash=row.get("backtest_hash") or "",
            compatibility_json=_loads("compatibility_json", {}),
            metrics_json=_loads("metrics_json", {}),
            engine_version=row.get("engine_version")
            or "qlib_strategy_adapter@1",
            recorder_id=row.get("recorder_id") or "",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_research_cross_validation(
        self, record: CrossValidationSummary
    ) -> None:
        """D1：写 research_cross_validation；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO research_cross_validation (
                  cv_hash, strategy_hash, backtest_hash, qlib_run_hash,
                  start_date, end_date, realism, execution_policy, status,
                  layer_results_json, attribution_json, metrics_side_by_side_json,
                  engine_version, storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(cv_hash) DO UPDATE SET
                  status=excluded.status,
                  layer_results_json=excluded.layer_results_json,
                  attribution_json=excluded.attribution_json,
                  metrics_side_by_side_json=excluded.metrics_side_by_side_json,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.cv_hash,
                    record.strategy_hash,
                    record.backtest_hash,
                    record.qlib_run_hash,
                    record.start_date,
                    record.end_date,
                    record.realism,
                    record.execution_policy,
                    record.status,
                    json.dumps(
                        record.layer_results_json or {}, ensure_ascii=False
                    ),
                    json.dumps(record.attribution_json or {}, ensure_ascii=False),
                    json.dumps(
                        record.metrics_side_by_side_json or {}, ensure_ascii=False
                    ),
                    record.engine_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_research_cross_validation(self, cv_hash: str) -> CrossValidationSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM research_cross_validation
                WHERE cv_hash=?
                """,
                [cv_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"research_cross_validation not found: {cv_hash!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return CrossValidationSummary(
            cv_hash=row["cv_hash"],
            strategy_hash=row["strategy_hash"],
            backtest_hash=row.get("backtest_hash") or "",
            qlib_run_hash=row.get("qlib_run_hash") or "",
            start_date=row.get("start_date") or "",
            end_date=row.get("end_date") or "",
            realism=row.get("realism") or "GROSS",
            execution_policy=row.get("execution_policy") or "NEXT_OPEN",
            status=row.get("status") or "FAILED",
            layer_results_json=_loads("layer_results_json", {}),
            attribution_json=_loads("attribution_json", {}),
            metrics_side_by_side_json=_loads("metrics_side_by_side_json", {}),
            engine_version=row.get("engine_version") or "qd_cross_validation@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_production_bundle(self, record: ProductionBundleSummary) -> None:
        """D1：写 production_bundle；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO production_bundle (
                  bundle_hash, strategy_hash, strategy_code, cv_hash,
                  backtest_hash, qlib_run_hash, dataset_hash, materialization_id,
                  model_artifact_id, model_version,
                  processor_hash, processor_artifact_uri, pipeline_digest,
                  universe_code, snapshot_id, execution_policy, realism, market_rule,
                  status, parent_bundle_hash, dependency_lock_json, feature_hashes_json,
                  engine_version, storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                ON CONFLICT(bundle_hash) DO UPDATE SET
                  status=excluded.status,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.bundle_hash,
                    record.strategy_hash,
                    record.strategy_code,
                    record.cv_hash,
                    record.backtest_hash,
                    record.qlib_run_hash,
                    record.dataset_hash,
                    record.materialization_id,
                    record.model_artifact_id,
                    record.model_version,
                    record.processor_hash,
                    record.processor_artifact_uri,
                    record.pipeline_digest,
                    record.universe_code,
                    record.snapshot_id,
                    record.execution_policy,
                    record.realism,
                    record.market_rule,
                    record.status,
                    record.parent_bundle_hash,
                    json.dumps(
                        record.dependency_lock_json or {}, ensure_ascii=False
                    ),
                    json.dumps(record.feature_hashes or [], ensure_ascii=False),
                    record.engine_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_production_bundle(self, bundle_hash: str) -> ProductionBundleSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_bundle WHERE bundle_hash=?",
                [bundle_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"production_bundle not found: {bundle_hash!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return ProductionBundleSummary(
            bundle_hash=row["bundle_hash"],
            strategy_hash=row["strategy_hash"],
            strategy_code=row.get("strategy_code") or "",
            cv_hash=row.get("cv_hash") or "",
            backtest_hash=row.get("backtest_hash") or "",
            qlib_run_hash=row.get("qlib_run_hash") or "",
            dataset_hash=row.get("dataset_hash") or "",
            materialization_id=row.get("materialization_id") or "",
            model_artifact_id=row.get("model_artifact_id") or "",
            model_version=row.get("model_version") or "",
            processor_hash=row.get("processor_hash") or "",
            processor_artifact_uri=row.get("processor_artifact_uri") or "",
            pipeline_digest=row.get("pipeline_digest") or "",
            universe_code=row.get("universe_code") or "",
            snapshot_id=row.get("snapshot_id") or "",
            execution_policy=row.get("execution_policy") or "NEXT_OPEN",
            realism=row.get("realism") or "GROSS",
            market_rule=row.get("market_rule") or "",
            status=row.get("status") or "DRAFT",
            parent_bundle_hash=row.get("parent_bundle_hash") or "",
            dependency_lock_json=_loads("dependency_lock_json", {}),
            feature_hashes=_loads("feature_hashes_json", []),
            engine_version=row.get("engine_version") or "qd_production_bridge@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_production_deployment(
        self, record: ProductionDeploymentSummary
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_deployment (
                  deployment_id, bundle_hash, strategy_code, status,
                  previous_bundle_hash, deployed_at, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deployment_id) DO UPDATE SET
                  status=excluded.status,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.deployment_id,
                    record.bundle_hash,
                    record.strategy_code,
                    record.status,
                    record.previous_bundle_hash,
                    record.deployed_at,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_production_deployment(
        self, deployment_id: str
    ) -> ProductionDeploymentSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_deployment WHERE deployment_id=?",
                [deployment_id],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"production_deployment not found: {deployment_id!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return ProductionDeploymentSummary(
            deployment_id=row["deployment_id"],
            bundle_hash=row["bundle_hash"],
            strategy_code=row.get("strategy_code") or "",
            status=row.get("status") or "DEPLOYED",
            previous_bundle_hash=row.get("previous_bundle_hash") or "",
            deployed_at=row.get("deployed_at"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def get_active_deployment(
        self, strategy_code: str
    ) -> ProductionDeploymentSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM production_deployment
                WHERE strategy_code=? AND status='DEPLOYED'
                ORDER BY deployed_at DESC
                LIMIT 1
                """,
                [strategy_code],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"active deployment not found: {strategy_code!r}")
        return self.get_production_deployment(rows[0]["deployment_id"])

    def upsert_deployment_run(
        self, record: ProductionDeploymentRunSummary
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_deployment_run (
                  run_id, bundle_hash, deployment_id, trading_date, status,
                  n_signals, n_intents, gate_json, storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  status=excluded.status,
                  gate_json=excluded.gate_json,
                  storage_uri=excluded.storage_uri
                """,
                [
                    record.run_id,
                    record.bundle_hash,
                    record.deployment_id,
                    record.trading_date,
                    record.status,
                    record.n_signals,
                    record.n_intents,
                    json.dumps(record.gate_json or {}, ensure_ascii=False),
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_deployment_run(self, run_id: str) -> ProductionDeploymentRunSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_deployment_run WHERE run_id=?",
                [run_id],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"deployment_run not found: {run_id!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        gate = json.loads(row.get("gate_json") or "{}")
        return ProductionDeploymentRunSummary(
            run_id=row["run_id"],
            bundle_hash=row["bundle_hash"],
            deployment_id=row.get("deployment_id") or "",
            trading_date=row.get("trading_date") or "",
            status=row.get("status") or "OK",
            n_signals=int(row.get("n_signals") or 0),
            n_intents=int(row.get("n_intents") or 0),
            gate_json=gate if isinstance(gate, dict) else {},
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_production_runtime(self, record: ProductionRuntimeSummary) -> None:
        """D1：写 production_runtime；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO production_runtime (
                  runtime_id, bundle_hash, strategy_code, market, environment,
                  status, session_phase, trading_date, started_at, last_heartbeat,
                  engine_version, storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(runtime_id) DO UPDATE SET
                  status=excluded.status,
                  session_phase=excluded.session_phase,
                  trading_date=excluded.trading_date,
                  last_heartbeat=excluded.last_heartbeat,
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.runtime_id,
                    record.bundle_hash,
                    record.strategy_code,
                    record.market,
                    record.environment,
                    record.status,
                    record.session_phase,
                    record.trading_date,
                    record.started_at,
                    record.last_heartbeat,
                    record.engine_version,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_production_runtime(self, runtime_id: str) -> ProductionRuntimeSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_runtime WHERE runtime_id=?",
                [runtime_id],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"production_runtime not found: {runtime_id!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return ProductionRuntimeSummary(
            runtime_id=row["runtime_id"],
            bundle_hash=row["bundle_hash"],
            strategy_code=row.get("strategy_code") or "",
            market=row.get("market") or "CN_A",
            environment=row.get("environment") or "PAPER",
            status=row.get("status") or "STARTING",
            session_phase=row.get("session_phase") or "PRE_MARKET",
            trading_date=row.get("trading_date") or "",
            started_at=row.get("started_at"),
            last_heartbeat=row.get("last_heartbeat"),
            engine_version=row.get("engine_version") or "qd_production_runtime@1",
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def append_runtime_event(self, record: ProductionRuntimeEventRecord) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_runtime_event (
                  event_id, runtime_id, event_type, trading_date, session_phase,
                  message, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                [
                    record.event_id,
                    record.runtime_id,
                    record.event_type,
                    record.trading_date,
                    record.session_phase,
                    record.message,
                    json.dumps(record.payload_json or {}, ensure_ascii=False),
                    record.created_at or _utc_now(),
                ],
            )
        except Exception:
            return

    def list_runtime_events(
        self, runtime_id: str, *, limit: int = 200
    ) -> list[ProductionRuntimeEventRecord]:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM production_runtime_event
                WHERE runtime_id=?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                [runtime_id, int(limit)],
            )
        except Exception:
            rows = []
        out: list[ProductionRuntimeEventRecord] = []
        for row in rows or []:
            payload = json.loads(row.get("payload_json") or "{}")
            out.append(
                ProductionRuntimeEventRecord(
                    event_id=row["event_id"],
                    runtime_id=row["runtime_id"],
                    event_type=row.get("event_type") or "",
                    trading_date=row.get("trading_date") or "",
                    session_phase=row.get("session_phase") or "",
                    message=row.get("message") or "",
                    payload_json=payload if isinstance(payload, dict) else {},
                    created_at=row.get("created_at"),
                )
            )
        return out

    def upsert_runtime_run(self, record: ProductionRuntimeRunSummary) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_runtime_run (
                  run_id, runtime_id, bundle_hash, idempotency_key,
                  trading_date, session_phase, status, n_signals, n_intents,
                  bridge_run_id, storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  status=excluded.status,
                  n_signals=excluded.n_signals,
                  n_intents=excluded.n_intents,
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.run_id,
                    record.runtime_id,
                    record.bundle_hash,
                    record.idempotency_key,
                    record.trading_date,
                    record.session_phase,
                    record.status,
                    record.n_signals,
                    record.n_intents,
                    record.bridge_run_id,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_runtime_run_by_idempotency(
        self, idempotency_key: str
    ) -> ProductionRuntimeRunSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_runtime_run WHERE idempotency_key=?",
                [idempotency_key],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"runtime_run idempotency not found: {idempotency_key!r}")
        return self._runtime_run_from_row(rows[0])

    def get_runtime_run(self, run_id: str) -> ProductionRuntimeRunSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_runtime_run WHERE run_id=?",
                [run_id],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"runtime_run not found: {run_id!r}")
        return self._runtime_run_from_row(rows[0])

    def _runtime_run_from_row(self, row: dict[str, Any]) -> ProductionRuntimeRunSummary:
        meta = json.loads(row.get("metadata_json") or "{}")
        return ProductionRuntimeRunSummary(
            run_id=row["run_id"],
            runtime_id=row["runtime_id"],
            bundle_hash=row["bundle_hash"],
            idempotency_key=row["idempotency_key"],
            trading_date=row.get("trading_date") or "",
            session_phase=row.get("session_phase") or "",
            status=row.get("status") or "OK",
            n_signals=int(row.get("n_signals") or 0),
            n_intents=int(row.get("n_intents") or 0),
            bridge_run_id=row.get("bridge_run_id") or "",
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_universe_ref(
        self,
        *,
        universe_code: str,
        pg_universe_id: int | None,
        market: str | None,
    ) -> None:
        d1_client.query(
            """
            INSERT INTO universe_ref (universe_code, pg_universe_id, market, synced_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(universe_code) DO UPDATE SET
              pg_universe_id=excluded.pg_universe_id,
              market=excluded.market,
              synced_at=excluded.synced_at
            """,
            [universe_code, pg_universe_id, market, _utc_now()],
        )

    def get_snapshot(self, snapshot_id: str) -> SnapshotRef:
        rows = d1_client.query(
            """
            SELECT i.path, i.checksum, v.dataset_code, v.version, v.r2_uri
            FROM data_snapshot_item i
            JOIN data_version v ON v.data_version_id = i.data_version_id
            WHERE i.snapshot_id = ?
            """,
            [snapshot_id],
        )
        if not rows:
            # 允许空 items 但仍要求 snapshot 行存在
            head = d1_client.query(
                "SELECT snapshot_id FROM data_snapshot WHERE snapshot_id=?",
                [snapshot_id],
            )
            if not head:
                raise KeyError(f"snapshot not found: {snapshot_id}")
        items = [
            DataVersionRef(
                dataset_code=str(r.get("dataset_code") or ""),
                version=str(r.get("version") or ""),
                checksum=r.get("checksum"),
                r2_uri=r.get("path") or r.get("r2_uri"),
            )
            for r in rows
        ]
        return SnapshotRef(snapshot_id=snapshot_id, items=items)

    def upsert_production_account(self, record: ProductionAccountSummary) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_account (
                  account_id, environment, market, status, currency,
                  available_cash, frozen_cash, market_value, equity,
                  realized_pnl, unrealized_pnl, total_pnl,
                  engine_version, storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                  status=excluded.status,
                  available_cash=excluded.available_cash,
                  frozen_cash=excluded.frozen_cash,
                  market_value=excluded.market_value,
                  equity=excluded.equity,
                  realized_pnl=excluded.realized_pnl,
                  unrealized_pnl=excluded.unrealized_pnl,
                  total_pnl=excluded.total_pnl,
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.account_id,
                    record.environment,
                    record.market,
                    record.status,
                    record.currency,
                    record.available_cash,
                    record.frozen_cash,
                    record.market_value,
                    record.equity,
                    record.realized_pnl,
                    record.unrealized_pnl,
                    record.total_pnl,
                    record.engine_version,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_production_account(self, account_id: str) -> ProductionAccountSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_account WHERE account_id=?",
                [account_id],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"production_account not found: {account_id!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return ProductionAccountSummary(
            account_id=row["account_id"],
            environment=row.get("environment") or "PAPER",
            market=row.get("market") or "CN_A",
            status=row.get("status") or "ACTIVE",
            currency=row.get("currency") or "CNY",
            available_cash=float(row.get("available_cash") or 0),
            frozen_cash=float(row.get("frozen_cash") or 0),
            market_value=float(row.get("market_value") or 0),
            equity=float(row.get("equity") or 0),
            realized_pnl=float(row.get("realized_pnl") or 0),
            unrealized_pnl=float(row.get("unrealized_pnl") or 0),
            total_pnl=float(row.get("total_pnl") or 0),
            engine_version=row.get("engine_version") or "qd_portfolio_service@1",
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_production_portfolio(
        self, record: ProductionPortfolioSummary
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_portfolio (
                  portfolio_id, account_id, runtime_id, bundle_hash, status,
                  trading_date, engine_version, storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(portfolio_id) DO UPDATE SET
                  runtime_id=excluded.runtime_id,
                  bundle_hash=excluded.bundle_hash,
                  status=excluded.status,
                  trading_date=excluded.trading_date,
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.portfolio_id,
                    record.account_id,
                    record.runtime_id,
                    record.bundle_hash,
                    record.status,
                    record.trading_date,
                    record.engine_version,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_production_portfolio(
        self, portfolio_id: str
    ) -> ProductionPortfolioSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_portfolio WHERE portfolio_id=?",
                [portfolio_id],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"production_portfolio not found: {portfolio_id!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return ProductionPortfolioSummary(
            portfolio_id=row["portfolio_id"],
            account_id=row["account_id"],
            runtime_id=row.get("runtime_id") or "",
            bundle_hash=row.get("bundle_hash") or "",
            status=row.get("status") or "ACTIVE",
            trading_date=row.get("trading_date") or "",
            engine_version=row.get("engine_version") or "qd_portfolio_service@1",
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def list_portfolios_by_account(
        self, account_id: str
    ) -> list[ProductionPortfolioSummary]:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_portfolio WHERE account_id=?",
                [account_id],
            )
        except Exception:
            rows = []
        out = []
        for row in rows or []:
            meta = json.loads(row.get("metadata_json") or "{}")
            out.append(
                ProductionPortfolioSummary(
                    portfolio_id=row["portfolio_id"],
                    account_id=row["account_id"],
                    runtime_id=row.get("runtime_id") or "",
                    bundle_hash=row.get("bundle_hash") or "",
                    status=row.get("status") or "ACTIVE",
                    trading_date=row.get("trading_date") or "",
                    engine_version=row.get("engine_version")
                    or "qd_portfolio_service@1",
                    storage_uri=row.get("storage_uri") or "",
                    created_at=row.get("created_at"),
                    metadata=meta if isinstance(meta, dict) else {},
                )
            )
        return out

    def upsert_production_position(
        self, record: ProductionPositionSummary
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_position (
                  portfolio_id, instrument_key, quantity, available_quantity,
                  frozen_quantity, avg_cost, market_value, currency, as_of, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(portfolio_id, instrument_key) DO UPDATE SET
                  quantity=excluded.quantity,
                  available_quantity=excluded.available_quantity,
                  frozen_quantity=excluded.frozen_quantity,
                  avg_cost=excluded.avg_cost,
                  market_value=excluded.market_value,
                  as_of=excluded.as_of,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.portfolio_id,
                    record.instrument_key,
                    record.quantity,
                    record.available_quantity,
                    record.frozen_quantity,
                    record.avg_cost,
                    record.market_value,
                    record.currency,
                    record.as_of,
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def list_positions(
        self, portfolio_id: str
    ) -> list[ProductionPositionSummary]:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_position WHERE portfolio_id=?",
                [portfolio_id],
            )
        except Exception:
            rows = []
        out = []
        for row in rows or []:
            meta = json.loads(row.get("metadata_json") or "{}")
            out.append(
                ProductionPositionSummary(
                    portfolio_id=row["portfolio_id"],
                    instrument_key=row["instrument_key"],
                    quantity=float(row.get("quantity") or 0),
                    available_quantity=float(row.get("available_quantity") or 0),
                    frozen_quantity=float(row.get("frozen_quantity") or 0),
                    avg_cost=float(row.get("avg_cost") or 0),
                    market_value=float(row.get("market_value") or 0),
                    currency=row.get("currency") or "CNY",
                    as_of=row.get("as_of"),
                    metadata=meta if isinstance(meta, dict) else {},
                )
            )
        return out

    def append_position_event(
        self, record: ProductionPositionEventRecord
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_position_event (
                  event_id, portfolio_id, account_id, event_type, instrument_key,
                  trading_date, quantity, price, cash_delta, fee, idempotency_key,
                  message, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                [
                    record.event_id,
                    record.portfolio_id,
                    record.account_id,
                    record.event_type,
                    record.instrument_key,
                    record.trading_date,
                    record.quantity,
                    record.price,
                    record.cash_delta,
                    record.fee,
                    record.idempotency_key,
                    record.message,
                    json.dumps(record.payload_json or {}, ensure_ascii=False),
                    record.created_at or _utc_now(),
                ],
            )
        except Exception:
            return

    def list_position_events(
        self, portfolio_id: str, *, limit: int = 500
    ) -> list[ProductionPositionEventRecord]:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM production_position_event
                WHERE portfolio_id=?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                [portfolio_id, int(limit)],
            )
        except Exception:
            rows = []
        out = []
        for row in rows or []:
            payload = json.loads(row.get("payload_json") or "{}")
            out.append(
                ProductionPositionEventRecord(
                    event_id=row["event_id"],
                    portfolio_id=row["portfolio_id"],
                    account_id=row.get("account_id") or "",
                    event_type=row.get("event_type") or "",
                    instrument_key=row.get("instrument_key") or "",
                    trading_date=row.get("trading_date") or "",
                    quantity=float(row.get("quantity") or 0),
                    price=float(row.get("price") or 0),
                    cash_delta=float(row.get("cash_delta") or 0),
                    fee=float(row.get("fee") or 0),
                    idempotency_key=row.get("idempotency_key") or "",
                    message=row.get("message") or "",
                    payload_json=payload if isinstance(payload, dict) else {},
                    created_at=row.get("created_at"),
                )
            )
        return out

    def upsert_portfolio_snapshot(
        self, record: ProductionPortfolioSnapshotSummary
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_portfolio_snapshot (
                  snapshot_id, account_id, portfolio_id, trading_date, knowledge_time,
                  cash, market_value, equity, realized_pnl, unrealized_pnl, total_pnl,
                  gross_exposure, net_exposure, runtime_id, bundle_hash, idempotency_key,
                  storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                  cash=excluded.cash,
                  market_value=excluded.market_value,
                  equity=excluded.equity,
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.snapshot_id,
                    record.account_id,
                    record.portfolio_id,
                    record.trading_date,
                    record.knowledge_time,
                    record.cash,
                    record.market_value,
                    record.equity,
                    record.realized_pnl,
                    record.unrealized_pnl,
                    record.total_pnl,
                    record.gross_exposure,
                    record.net_exposure,
                    record.runtime_id,
                    record.bundle_hash,
                    record.idempotency_key,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_portfolio_snapshot(
        self, snapshot_id: str
    ) -> ProductionPortfolioSnapshotSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_portfolio_snapshot WHERE snapshot_id=?",
                [snapshot_id],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"portfolio_snapshot not found: {snapshot_id!r}")
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return ProductionPortfolioSnapshotSummary(
            snapshot_id=row["snapshot_id"],
            account_id=row["account_id"],
            portfolio_id=row["portfolio_id"],
            trading_date=row.get("trading_date") or "",
            knowledge_time=row.get("knowledge_time"),
            cash=float(row.get("cash") or 0),
            market_value=float(row.get("market_value") or 0),
            equity=float(row.get("equity") or 0),
            realized_pnl=float(row.get("realized_pnl") or 0),
            unrealized_pnl=float(row.get("unrealized_pnl") or 0),
            total_pnl=float(row.get("total_pnl") or 0),
            gross_exposure=float(row.get("gross_exposure") or 0),
            net_exposure=float(row.get("net_exposure") or 0),
            runtime_id=row.get("runtime_id") or "",
            bundle_hash=row.get("bundle_hash") or "",
            idempotency_key=row.get("idempotency_key") or "",
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_portfolio_apply(
        self, record: ProductionPortfolioApplySummary
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO production_portfolio_apply (
                  apply_id, account_id, portfolio_id, idempotency_key, trading_date,
                  status, n_deltas, n_events, snapshot_id, runtime_id, run_id,
                  storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(apply_id) DO UPDATE SET
                  status=excluded.status,
                  n_deltas=excluded.n_deltas,
                  n_events=excluded.n_events,
                  snapshot_id=excluded.snapshot_id,
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.apply_id,
                    record.account_id,
                    record.portfolio_id,
                    record.idempotency_key,
                    record.trading_date,
                    record.status,
                    record.n_deltas,
                    record.n_events,
                    record.snapshot_id,
                    record.runtime_id,
                    record.run_id,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_apply_by_idempotency(
        self, idempotency_key: str
    ) -> ProductionPortfolioApplySummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM production_portfolio_apply WHERE idempotency_key=?",
                [idempotency_key],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"portfolio_apply idempotency not found: {idempotency_key!r}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return ProductionPortfolioApplySummary(
            apply_id=row["apply_id"],
            account_id=row["account_id"],
            portfolio_id=row["portfolio_id"],
            idempotency_key=row["idempotency_key"],
            trading_date=row.get("trading_date") or "",
            status=row.get("status") or "OK",
            n_deltas=int(row.get("n_deltas") or 0),
            n_events=int(row.get("n_events") or 0),
            snapshot_id=row.get("snapshot_id") or "",
            runtime_id=row.get("runtime_id") or "",
            run_id=row.get("run_id") or "",
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_risk_policy(self, record: RiskPolicySummary) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO risk_policy (
                  policy_hash, policy_code, policy_version, engine_version,
                  storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_hash) DO UPDATE SET
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.policy_hash,
                    record.policy_code,
                    record.policy_version,
                    record.engine_version,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_risk_policy(
        self, policy_code: str, policy_version: str
    ) -> RiskPolicySummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM risk_policy WHERE policy_code=? AND policy_version=?",
                [policy_code, policy_version],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"risk_policy not found: {policy_code!r}@{policy_version!r}"
            )
        return self._risk_policy_from_row(rows[0])

    def get_risk_policy_by_hash(self, policy_hash: str) -> RiskPolicySummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM risk_policy WHERE policy_hash=?",
                [policy_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"risk_policy not found: {policy_hash!r}")
        return self._risk_policy_from_row(rows[0])

    def _risk_policy_from_row(self, row: dict[str, Any]) -> RiskPolicySummary:
        meta = json.loads(row.get("metadata_json") or "{}")
        return RiskPolicySummary(
            policy_hash=row["policy_hash"],
            policy_code=row["policy_code"],
            policy_version=row["policy_version"],
            engine_version=row.get("engine_version") or "qd_risk_engine@1",
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_risk_run(self, record: RiskRunSummary) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO risk_run (
                  risk_run_id, idempotency_key, policy_hash, account_id,
                  portfolio_id, apply_id, trading_date, verdict,
                  n_intents, n_violations, storage_uri, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(risk_run_id) DO UPDATE SET
                  verdict=excluded.verdict,
                  n_intents=excluded.n_intents,
                  n_violations=excluded.n_violations,
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.risk_run_id,
                    record.idempotency_key,
                    record.policy_hash,
                    record.account_id,
                    record.portfolio_id,
                    record.apply_id,
                    record.trading_date,
                    record.verdict,
                    record.n_intents,
                    record.n_violations,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_risk_run_by_idempotency(self, idempotency_key: str) -> RiskRunSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM risk_run WHERE idempotency_key=?",
                [idempotency_key],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"risk_run idempotency not found: {idempotency_key!r}")
        return self._risk_run_from_row(rows[0])

    def get_risk_run(self, risk_run_id: str) -> RiskRunSummary:
        try:
            rows = d1_client.query(
                "SELECT * FROM risk_run WHERE risk_run_id=?",
                [risk_run_id],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(f"risk_run not found: {risk_run_id!r}")
        return self._risk_run_from_row(rows[0])

    def _risk_run_from_row(self, row: dict[str, Any]) -> RiskRunSummary:
        meta = json.loads(row.get("metadata_json") or "{}")
        return RiskRunSummary(
            risk_run_id=row["risk_run_id"],
            idempotency_key=row["idempotency_key"],
            policy_hash=row.get("policy_hash") or "",
            account_id=row.get("account_id") or "",
            portfolio_id=row.get("portfolio_id") or "",
            apply_id=row.get("apply_id") or "",
            trading_date=row.get("trading_date") or "",
            verdict=row.get("verdict") or "ALLOW",
            n_intents=int(row.get("n_intents") or 0),
            n_violations=int(row.get("n_violations") or 0),
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def append_risk_decision_event(
        self, record: RiskDecisionEventRecord
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO risk_decision_event (
                  event_id, risk_run_id, rule_code, decision, severity,
                  instrument_key, message, original_value, limit_value,
                  payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                [
                    record.event_id,
                    record.risk_run_id,
                    record.rule_code,
                    record.decision,
                    record.severity,
                    record.instrument_key,
                    record.message,
                    record.original_value,
                    record.limit_value,
                    json.dumps(record.payload_json or {}, ensure_ascii=False),
                    record.created_at or _utc_now(),
                ],
            )
        except Exception:
            return

    def upsert_oms_order(self, record: OmsOrderSummary) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO oms_order (
                  order_id, client_order_id, broker_order_id, account_id,
                  portfolio_id, risk_run_id, policy_hash, instrument_key,
                  side, order_type, tif, quantity, limit_price,
                  filled_quantity, avg_fill_price, status, version,
                  idempotency_key, trading_date, engine_version, storage_uri,
                  created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                  broker_order_id=excluded.broker_order_id,
                  filled_quantity=excluded.filled_quantity,
                  avg_fill_price=excluded.avg_fill_price,
                  status=excluded.status,
                  version=excluded.version,
                  limit_price=excluded.limit_price,
                  quantity=excluded.quantity,
                  storage_uri=excluded.storage_uri,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.order_id,
                    record.client_order_id,
                    record.broker_order_id,
                    record.account_id,
                    record.portfolio_id,
                    record.risk_run_id,
                    record.policy_hash,
                    record.instrument_key,
                    record.side,
                    record.order_type,
                    record.tif,
                    record.quantity,
                    record.limit_price,
                    record.filled_quantity,
                    record.avg_fill_price,
                    record.status,
                    record.version,
                    record.idempotency_key,
                    record.trading_date,
                    record.engine_version,
                    record.storage_uri,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_oms_order(self, order_id: str) -> OmsOrderSummary:
        rows = d1_client.query(
            "SELECT * FROM oms_order WHERE order_id = ? LIMIT 1", [order_id]
        )
        if not rows:
            raise KeyError(f"oms_order not found: {order_id!r}")
        return self._oms_order_from_row(rows[0])

    def get_order_by_idempotency(self, idempotency_key: str) -> OmsOrderSummary:
        rows = d1_client.query(
            "SELECT * FROM oms_order WHERE idempotency_key = ? LIMIT 1",
            [idempotency_key],
        )
        if not rows:
            raise KeyError(f"oms idempotency not found: {idempotency_key!r}")
        return self._oms_order_from_row(rows[0])

    def list_oms_orders(
        self, *, account_id: str = "", status: str = ""
    ) -> list[OmsOrderSummary]:
        try:
            sql = "SELECT * FROM oms_order WHERE 1=1"
            args: list[Any] = []
            if account_id:
                sql += " AND account_id = ?"
                args.append(account_id)
            if status:
                sql += " AND status = ?"
                args.append(status)
            rows = d1_client.query(sql, args)
            return [self._oms_order_from_row(r) for r in rows or []]
        except Exception:
            return []

    def _oms_order_from_row(self, row: dict[str, Any]) -> OmsOrderSummary:
        meta = row.get("metadata_json") or "{}"
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return OmsOrderSummary(
            order_id=row["order_id"],
            client_order_id=row.get("client_order_id") or "",
            broker_order_id=row.get("broker_order_id") or "",
            account_id=row.get("account_id") or "",
            portfolio_id=row.get("portfolio_id") or "",
            risk_run_id=row.get("risk_run_id") or "",
            policy_hash=row.get("policy_hash") or "",
            instrument_key=row.get("instrument_key") or "",
            side=row.get("side") or "BUY",
            order_type=row.get("order_type") or "MARKET",
            tif=row.get("tif") or "DAY",
            quantity=float(row.get("quantity") or 0),
            limit_price=row.get("limit_price"),
            filled_quantity=float(row.get("filled_quantity") or 0),
            avg_fill_price=float(row.get("avg_fill_price") or 0),
            status=row.get("status") or "CREATED",
            version=int(row.get("version") or 1),
            idempotency_key=row.get("idempotency_key") or "",
            trading_date=row.get("trading_date") or "",
            engine_version=row.get("engine_version") or "qd_oms@1",
            storage_uri=row.get("storage_uri") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_oms_order_version(self, version: Any) -> None:
        try:
            payload = (
                version.model_dump(mode="json")
                if hasattr(version, "model_dump")
                else dict(version)
            )
            d1_client.query(
                """
                INSERT INTO oms_order_version (
                  order_id, version, quantity, limit_price, status,
                  created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id, version) DO UPDATE SET
                  quantity=excluded.quantity,
                  limit_price=excluded.limit_price,
                  status=excluded.status,
                  metadata_json=excluded.metadata_json
                """,
                [
                    payload.get("order_id"),
                    payload.get("version"),
                    payload.get("quantity") or 0,
                    payload.get("limit_price"),
                    payload.get("status") or "",
                    payload.get("created_at") or _utc_now(),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def append_order_event(self, record: OmsOrderEventRecord) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO oms_order_event (
                  event_id, order_id, event_type, previous_status, new_status,
                  source, message, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                [
                    record.event_id,
                    record.order_id,
                    record.event_type,
                    record.previous_status,
                    record.new_status,
                    record.source,
                    record.message,
                    json.dumps(record.payload_json or {}, ensure_ascii=False),
                    record.created_at or _utc_now(),
                ],
            )
        except Exception:
            return

    def list_order_events(self, order_id: str) -> list[OmsOrderEventRecord]:
        try:
            rows = d1_client.query(
                "SELECT * FROM oms_order_event WHERE order_id = ? ORDER BY created_at",
                [order_id],
            )
            out: list[OmsOrderEventRecord] = []
            for row in rows or []:
                payload = row.get("payload_json") or "{}"
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {}
                out.append(
                    OmsOrderEventRecord(
                        event_id=row["event_id"],
                        order_id=row["order_id"],
                        event_type=row.get("event_type") or "",
                        previous_status=row.get("previous_status") or "",
                        new_status=row.get("new_status") or "",
                        source=row.get("source") or "OMS",
                        message=row.get("message") or "",
                        payload_json=payload if isinstance(payload, dict) else {},
                        created_at=row.get("created_at"),
                    )
                )
            return out
        except Exception:
            return []

    def upsert_fill(self, record: OmsFillSummary) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO oms_fill (
                  fill_id, order_id, instrument_key, side, quantity, price,
                  fee, trading_date, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fill_id) DO UPDATE SET
                  quantity=excluded.quantity,
                  price=excluded.price,
                  fee=excluded.fee,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.fill_id,
                    record.order_id,
                    record.instrument_key,
                    record.side,
                    record.quantity,
                    record.price,
                    record.fee,
                    record.trading_date,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def list_oms_fills(self, order_id: str) -> list[OmsFillSummary]:
        try:
            rows = d1_client.query(
                "SELECT * FROM oms_fill WHERE order_id = ?", [order_id]
            )
            out: list[OmsFillSummary] = []
            for row in rows or []:
                meta = row.get("metadata_json") or "{}"
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                out.append(
                    OmsFillSummary(
                        fill_id=row["fill_id"],
                        order_id=row["order_id"],
                        instrument_key=row.get("instrument_key") or "",
                        side=row.get("side") or "BUY",
                        quantity=float(row.get("quantity") or 0),
                        price=float(row.get("price") or 0),
                        fee=float(row.get("fee") or 0),
                        trading_date=row.get("trading_date") or "",
                        created_at=row.get("created_at"),
                        metadata=meta if isinstance(meta, dict) else {},
                    )
                )
            return out
        except Exception:
            return []

    def enqueue_outbox(self, record: OmsOutboxRecord) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO oms_outbox (
                  outbox_id, aggregate_type, aggregate_id, event_type,
                  status, payload_json, created_at, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(outbox_id) DO UPDATE SET
                  status=excluded.status,
                  payload_json=excluded.payload_json,
                  sent_at=excluded.sent_at
                """,
                [
                    record.outbox_id,
                    record.aggregate_type,
                    record.aggregate_id,
                    record.event_type,
                    record.status,
                    json.dumps(record.payload_json or {}, ensure_ascii=False),
                    record.created_at or _utc_now(),
                    record.sent_at,
                ],
            )
        except Exception:
            return

    def list_outbox(self, *, limit: int = 100) -> list[OmsOutboxRecord]:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM oms_outbox WHERE status = 'PENDING'
                ORDER BY created_at LIMIT ?
                """,
                [limit],
            )
            out: list[OmsOutboxRecord] = []
            for row in rows or []:
                payload = row.get("payload_json") or "{}"
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {}
                out.append(
                    OmsOutboxRecord(
                        outbox_id=row["outbox_id"],
                        aggregate_type=row.get("aggregate_type") or "ORDER",
                        aggregate_id=row.get("aggregate_id") or "",
                        event_type=row.get("event_type") or "",
                        status=row.get("status") or "PENDING",
                        payload_json=payload if isinstance(payload, dict) else {},
                        created_at=row.get("created_at"),
                        sent_at=row.get("sent_at"),
                    )
                )
            return out
        except Exception:
            return []

    def mark_outbox(self, outbox_id: str, status: str) -> None:
        try:
            sent = _utc_now() if status == "SENT" else None
            d1_client.query(
                "UPDATE oms_outbox SET status = ?, sent_at = COALESCE(?, sent_at) WHERE outbox_id = ?",
                [status, sent, outbox_id],
            )
        except Exception:
            return

    def upsert_cancel_request(self, request: Any) -> None:
        try:
            payload = (
                request.model_dump(mode="json")
                if hasattr(request, "model_dump")
                else dict(request)
            )
            d1_client.query(
                """
                INSERT INTO oms_cancel_request (
                  request_id, order_id, status, reason, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET status=excluded.status
                """,
                [
                    payload.get("request_id"),
                    payload.get("order_id"),
                    payload.get("status") or "PENDING",
                    payload.get("reason") or "",
                    payload.get("created_at") or _utc_now(),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def upsert_replace_request(self, request: Any) -> None:
        try:
            payload = (
                request.model_dump(mode="json")
                if hasattr(request, "model_dump")
                else dict(request)
            )
            d1_client.query(
                """
                INSERT INTO oms_replace_request (
                  request_id, order_id, status, quantity, limit_price,
                  created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET status=excluded.status
                """,
                [
                    payload.get("request_id"),
                    payload.get("order_id"),
                    payload.get("status") or "PENDING",
                    payload.get("quantity"),
                    payload.get("limit_price"),
                    payload.get("created_at") or _utc_now(),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def upsert_broker_session(self, record: BrokerSessionSummary) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO broker_session (
                  session_id, broker_id, execution_mode, status,
                  engine_version, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  status=excluded.status,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.session_id,
                    record.broker_id,
                    record.execution_mode,
                    record.status,
                    record.engine_version,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def upsert_broker_order_link(self, record: BrokerOrderLinkRecord) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO broker_order_link (
                  order_id, client_order_id, broker_order_id, broker_id,
                  account_id, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                  broker_order_id=excluded.broker_order_id,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.order_id,
                    record.client_order_id,
                    record.broker_order_id or None,
                    record.broker_id,
                    record.account_id,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_order_link_by_client_id(
        self, client_order_id: str
    ) -> BrokerOrderLinkRecord:
        rows = d1_client.query(
            "SELECT * FROM broker_order_link WHERE client_order_id = ? LIMIT 1",
            [client_order_id],
        )
        if not rows:
            raise KeyError(f"broker link client not found: {client_order_id!r}")
        return self._broker_link_from_row(rows[0])

    def get_order_link_by_broker_id(
        self, broker_id: str, broker_order_id: str
    ) -> BrokerOrderLinkRecord:
        rows = d1_client.query(
            """
            SELECT * FROM broker_order_link
            WHERE broker_id = ? AND broker_order_id = ? LIMIT 1
            """,
            [broker_id, broker_order_id],
        )
        if not rows:
            raise KeyError(
                f"broker link not found: {broker_id!r}/{broker_order_id!r}"
            )
        return self._broker_link_from_row(rows[0])

    def _broker_link_from_row(self, row: dict[str, Any]) -> BrokerOrderLinkRecord:
        meta = row.get("metadata_json") or "{}"
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return BrokerOrderLinkRecord(
            order_id=row["order_id"],
            client_order_id=row.get("client_order_id") or "",
            broker_order_id=row.get("broker_order_id") or "",
            broker_id=row.get("broker_id") or "",
            account_id=row.get("account_id") or "",
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def try_record_execution_dedup(
        self, broker_id: str, broker_execution_id: str
    ) -> bool:
        try:
            rows = d1_client.query(
                """
                SELECT 1 FROM broker_execution_dedup
                WHERE broker_id = ? AND broker_execution_id = ? LIMIT 1
                """,
                [broker_id, broker_execution_id],
            )
            if rows:
                return False
            d1_client.query(
                """
                INSERT INTO broker_execution_dedup (
                  broker_id, broker_execution_id, created_at
                ) VALUES (?, ?, ?)
                """,
                [broker_id, broker_execution_id, _utc_now()],
            )
            return True
        except Exception:
            return True

    def append_broker_event_index(
        self, record: BrokerEventIndexRecord
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO broker_event_index (
                  event_id, broker_id, received_at, storage_uri,
                  checksum, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                [
                    record.event_id,
                    record.broker_id,
                    record.received_at or _utc_now(),
                    record.storage_uri,
                    record.checksum,
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def upsert_reconciliation_run(
        self, record: ReconciliationRunSummary
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO reconciliation_run (
                  run_id, account_id, portfolio_id, broker_id, mode,
                  started_at, completed_at, snapshot_id, finding_count,
                  critical_count, gate_blocked, engine_version, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  completed_at=excluded.completed_at,
                  finding_count=excluded.finding_count,
                  critical_count=excluded.critical_count,
                  gate_blocked=excluded.gate_blocked,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.run_id,
                    record.account_id,
                    record.portfolio_id,
                    record.broker_id,
                    record.mode,
                    record.started_at,
                    record.completed_at,
                    record.snapshot_id,
                    int(record.finding_count),
                    int(record.critical_count),
                    1 if record.gate_blocked else 0,
                    record.engine_version,
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def upsert_reconciliation_finding(
        self, record: ReconciliationFindingSummary
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO reconciliation_finding (
                  finding_id, run_id, type, severity, status, entity_type,
                  entity_id, expected_json, actual_json, difference_json,
                  detected_at, resolved_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(finding_id) DO UPDATE SET
                  status=excluded.status,
                  resolved_at=excluded.resolved_at,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.finding_id,
                    record.run_id,
                    record.type,
                    record.severity,
                    record.status,
                    record.entity_type,
                    record.entity_id,
                    json.dumps(record.expected or {}, ensure_ascii=False),
                    json.dumps(record.actual or {}, ensure_ascii=False),
                    json.dumps(record.difference or {}, ensure_ascii=False),
                    record.detected_at,
                    record.resolved_at,
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def list_reconciliation_findings(
        self,
        *,
        run_id: str = "",
        account_id: str = "",
        status: str = "",
    ) -> list[ReconciliationFindingSummary]:
        # D1 列表简化：失败返回空（单测走 LocalJson）
        try:
            sql = "SELECT * FROM reconciliation_finding WHERE 1=1"
            params: list[Any] = []
            if run_id:
                sql += " AND run_id=?"
                params.append(run_id)
            if status:
                sql += " AND status=?"
                params.append(status)
            rows = d1_client.query(sql, params) or []
            out: list[ReconciliationFindingSummary] = []
            for r in rows:
                meta = json.loads(r.get("metadata_json") or "{}")
                if account_id and str(meta.get("account_id") or "") != account_id:
                    continue
                out.append(
                    ReconciliationFindingSummary(
                        finding_id=r["finding_id"],
                        run_id=r.get("run_id") or "",
                        type=r.get("type") or "",
                        severity=r.get("severity") or "",
                        status=r.get("status") or "",
                        entity_type=r.get("entity_type") or "",
                        entity_id=r.get("entity_id") or "",
                        expected=json.loads(r.get("expected_json") or "{}"),
                        actual=json.loads(r.get("actual_json") or "{}"),
                        difference=json.loads(r.get("difference_json") or "{}"),
                        detected_at=r.get("detected_at"),
                        resolved_at=r.get("resolved_at"),
                        metadata=meta,
                    )
                )
            return out
        except Exception:
            return []

    def append_broker_snapshot_index(
        self, record: BrokerSnapshotIndexRecord
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO broker_snapshot_index (
                  snapshot_id, broker_id, account_id, captured_at,
                  storage_uri, checksum, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO NOTHING
                """,
                [
                    record.snapshot_id,
                    record.broker_id,
                    record.account_id,
                    record.captured_at,
                    record.storage_uri,
                    record.checksum,
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_reconciliation_cursor(
        self,
        account_id: str,
        *,
        broker_id: str = "",
        cursor_type: str = "EXECUTION",
    ) -> ReconciliationCursorRecord:
        rows = d1_client.query(
            """
            SELECT * FROM reconciliation_cursor
            WHERE account_id=? AND broker_id=? AND cursor_type=?
            """,
            [account_id, broker_id, cursor_type],
        )
        if not rows:
            raise KeyError("cursor not found")
        r = rows[0]
        return ReconciliationCursorRecord(
            account_id=r["account_id"],
            broker_id=r.get("broker_id") or "",
            cursor_type=r.get("cursor_type") or "",
            cursor_value=r.get("cursor_value") or "",
            updated_at=r.get("updated_at"),
        )

    def set_reconciliation_cursor(
        self, record: ReconciliationCursorRecord
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO reconciliation_cursor (
                  account_id, broker_id, cursor_type, cursor_value, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id, broker_id, cursor_type) DO UPDATE SET
                  cursor_value=excluded.cursor_value,
                  updated_at=excluded.updated_at
                """,
                [
                    record.account_id,
                    record.broker_id,
                    record.cursor_type,
                    record.cursor_value,
                    record.updated_at or _utc_now(),
                ],
            )
        except Exception:
            return

    def get_reconciliation_gate(
        self, account_id: str
    ) -> ReconciliationGateRecord:
        rows = d1_client.query(
            "SELECT * FROM reconciliation_gate WHERE account_id=?",
            [account_id],
        )
        if not rows:
            raise KeyError("gate not found")
        r = rows[0]
        return ReconciliationGateRecord(
            account_id=r["account_id"],
            blocked=bool(r.get("blocked")),
            reason=r.get("reason") or "",
            finding_id=r.get("finding_id") or "",
            updated_at=r.get("updated_at"),
            metadata=json.loads(r.get("metadata_json") or "{}"),
        )

    def set_reconciliation_gate(
        self, record: ReconciliationGateRecord
    ) -> None:
        try:
            d1_client.query(
                """
                INSERT INTO reconciliation_gate (
                  account_id, blocked, reason, finding_id, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                  blocked=excluded.blocked,
                  reason=excluded.reason,
                  finding_id=excluded.finding_id,
                  updated_at=excluded.updated_at,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.account_id,
                    1 if record.blocked else 0,
                    record.reason,
                    record.finding_id,
                    record.updated_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return


def get_default_registry(root: Path | None = None) -> ResearchRegistry:
    """已配置 D1 Research 则用远端，否则本地 JSON。"""
    if d1_client.configured():
        return D1ResearchRegistry()
    return LocalJsonRegistry(root=root)


def new_snapshot_id(prefix: str = "snap") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _split_ref(ref: str) -> tuple[str, str]:
    text = str(ref or "").strip()
    if "@" not in text:
        raise ValueError(f"ref must be code@version, got {ref!r}")
    code, version = text.split("@", 1)
    if not code or not version:
        raise ValueError(f"ref must be code@version, got {ref!r}")
    return code, version
