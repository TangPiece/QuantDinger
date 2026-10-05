"""ExperimentRunner：Dataset→Model→Prediction→Signal→Manifest→Registry→MLflow。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.research_data.contracts import (
    ExperimentDefinition,
    ExperimentManifest,
)
from app.services.research_data.model_training import ModelTrainer
from app.services.research_data.model_training.artifact_store import compute_config_digest
from app.services.research_data.qlib_adapter import QlibAdapter, VersionResolver
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.signal import SignalPipeline
from app.services.research_data.signal.artifact_store import SignalArtifactStore

from .fingerprint import compute_repro_fingerprint, experiment_id_from_fingerprint
from .manifest_store import ExperimentManifestStore
from .metrics import merge_experiment_metrics
from .mlflow_bridge import log_experiment_run
from .specs import ExperimentSpec
from .version import EXPERIMENT_PIPELINE_VERSION


@dataclass
class ExperimentResult:
    """一次实验运行摘要（用于复现比较与验收）。"""

    experiment_id: str
    name: str
    dataset_hash: str
    bundle_hash: str
    repro_fingerprint: str
    prediction_fingerprint: str
    model_artifact_id: str
    signal_artifact_id: str
    signal_run_id: str
    metrics: dict[str, Any] = field(default_factory=dict)
    manifest_uri: str = ""
    mlflow_run_id: Optional[str] = None
    model_version_ref: str = ""
    strategy_version: str = ""
    processor_ref: Optional[str] = None
    snapshot_id: str = ""
    dataset_ref: str = ""


class ExperimentRunner:
    """顶层编排：训练 + 信号 + manifest + Registry + MLflow。"""

    def __init__(
        self,
        qlib_adapter: QlibAdapter,
        registry: ResearchRegistry,
        *,
        model_trainer: ModelTrainer | None = None,
        signal_pipeline: SignalPipeline | None = None,
        manifest_store: ExperimentManifestStore | None = None,
        signal_artifact_store: SignalArtifactStore | None = None,
    ) -> None:
        self._adapter = qlib_adapter
        self._registry = registry
        self._trainer = model_trainer or ModelTrainer(qlib_adapter, registry)
        self._signals = signal_pipeline or SignalPipeline(
            registry, artifact_store=signal_artifact_store
        )
        self._manifests = manifest_store or ExperimentManifestStore()
        self._versions = VersionResolver(
            qlib_adapter._query, registry  # noqa: SLF001
        )

    def run(self, spec: ExperimentSpec) -> ExperimentResult:
        """执行完整实验；Experiment 登记仅由此处完成。"""
        seed = spec.resolved_seed()
        # 保证 train.seed 与实验 seed 一致
        train_spec = spec.train.model_copy(update={"seed": seed})

        bundle = self._versions.resolve(train_spec.dataset_spec.dataset_ref)
        model_def = self._trainer._resolve_model(train_spec)  # noqa: SLF001
        merged_config = dict(model_def.config or {})
        merged_config.update(train_spec.config_override or {})
        merged_config["seed"] = seed
        config_digest = compute_config_digest(merged_config)
        model_ref = train_spec.resolved_model_ref(model_def)

        strategy = spec.signal.strategy
        portfolio = spec.signal.portfolio
        strategy_digest = strategy.strategy_digest()
        portfolio_digest = portfolio.portfolio_digest()

        repro = compute_repro_fingerprint(
            dataset_hash=bundle.dataset_hash,
            bundle_hash=bundle.bundle_hash,
            model_ref=model_ref,
            config_digest=config_digest,
            seed=seed,
            strategy_digest=strategy_digest,
            portfolio_digest=portfolio_digest,
        )
        experiment_id = experiment_id_from_fingerprint(repro)

        train_result = self._trainer.train(train_spec)
        signal_result = self._signals.run(
            train_result.predictions,
            spec.signal,
            snapshot_id=bundle.snapshot_id,
        )

        metrics = merge_experiment_metrics(
            train_metrics=train_result.metrics,
            signals=signal_result.signals,
            cash_weight=signal_result.cash_weight,
            n_positions=len(signal_result.positions),
        )

        feature_refs: list[str] = []
        try:
            handle = self._registry.get_dataset(train_spec.dataset_spec.dataset_ref)
            feature_refs = list(handle.definition.features or [])
        except Exception:
            feature_refs = []

        processor_ref = (
            train_result.processor_version
            if train_result.processor_version != "none"
            else None
        )
        segments = train_spec.dataset_spec.segments.canonical_dict()

        model_uri = ""
        try:
            model_uri = self._registry.get_artifact(
                train_result.artifact_id
            ).storage_uri
        except Exception:
            model_uri = train_result.artifact_uri

        manifest = ExperimentManifest(
            experiment_id=experiment_id,
            name=spec.name,
            experiment_pipeline_version=EXPERIMENT_PIPELINE_VERSION,
            repro_fingerprint=repro,
            dataset_ref=train_spec.dataset_spec.dataset_ref,
            dataset_hash=train_result.dataset_hash,
            bundle_hash=train_result.bundle_hash,
            snapshot_id=bundle.snapshot_id,
            feature_refs=feature_refs,
            processor_ref=processor_ref,
            model={
                "code": model_def.code,
                "version": model_def.version,
                "ref": model_ref,
                "config_digest": config_digest,
                "seed": seed,
            },
            strategy={
                "version": strategy.strategy_version,
                "digest": strategy_digest,
            },
            portfolio={
                "code": portfolio.portfolio_code,
                "digest": portfolio_digest,
            },
            segments=segments,
            model_artifact_id=train_result.artifact_id,
            model_artifact_uri=model_uri,
            signal_artifact_id=signal_result.artifact_id,
            signal_artifact_uri=signal_result.artifact_uri,
            signal_run_id=signal_result.signal_run_id,
            prediction_fingerprint=signal_result.prediction_fingerprint,
            metrics=metrics,
            seed=seed,
        )

        mlflow_run_id = log_experiment_run(
            experiment_name=spec.name,
            experiment_id=experiment_id,
            params={
                "experiment_id": experiment_id,
                "dataset_hash": train_result.dataset_hash,
                "bundle_hash": train_result.bundle_hash,
                "model_version": model_ref,
                "model_artifact_id": train_result.artifact_id,
                "signal_artifact_id": signal_result.artifact_id,
                "strategy_version": strategy.strategy_version,
                "repro_fingerprint": repro,
                "processor_ref": processor_ref or "",
                "seed": seed,
            },
            metrics=metrics,
            tags={
                "qd.bundle_hash": train_result.bundle_hash,
                "qd.model_artifact_id": train_result.artifact_id,
            },
        )
        manifest = manifest.model_copy(update={"mlflow_run_id": mlflow_run_id})
        manifest_uri = self._manifests.write(manifest)

        definition = ExperimentDefinition(
            experiment_id=experiment_id,
            name=spec.name,
            dataset_ref=train_spec.dataset_spec.dataset_ref,
            snapshot_id=bundle.snapshot_id,
            dataset_hash=train_result.dataset_hash,
            model_version_ref=model_ref,
            mlflow_run_id=mlflow_run_id,
            parameters={
                "config_digest": config_digest,
                "seed": seed,
                "strategy_digest": strategy_digest,
                "portfolio_digest": portfolio_digest,
                "experiment_pipeline_version": EXPERIMENT_PIPELINE_VERSION,
            },
            feature_refs=feature_refs,
            processor_ref=processor_ref,
            strategy_version=strategy.strategy_version,
            model_artifact_id=train_result.artifact_id,
            signal_artifact_id=signal_result.artifact_id,
            signal_run_id=signal_result.signal_run_id,
            bundle_hash=train_result.bundle_hash,
            prediction_fingerprint=signal_result.prediction_fingerprint,
            repro_fingerprint=repro,
            metrics=metrics,
            manifest_uri=manifest_uri,
            status="COMPLETED",
            segments=segments,
        )
        self._registry.upsert_experiment(definition)

        return ExperimentResult(
            experiment_id=experiment_id,
            name=spec.name,
            dataset_hash=train_result.dataset_hash,
            bundle_hash=train_result.bundle_hash,
            repro_fingerprint=repro,
            prediction_fingerprint=signal_result.prediction_fingerprint,
            model_artifact_id=train_result.artifact_id,
            signal_artifact_id=signal_result.artifact_id,
            signal_run_id=signal_result.signal_run_id,
            metrics=metrics,
            manifest_uri=manifest_uri,
            mlflow_run_id=mlflow_run_id,
            model_version_ref=model_ref,
            strategy_version=strategy.strategy_version,
            processor_ref=processor_ref,
            snapshot_id=bundle.snapshot_id,
            dataset_ref=train_spec.dataset_spec.dataset_ref,
        )
