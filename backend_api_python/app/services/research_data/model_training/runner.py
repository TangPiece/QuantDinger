"""ModelTrainer：DatasetH → LightGBM fit/eval/predict → Artifact + Registry。"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import pandas as pd

from app.services.research_data.contracts import (
    ExperimentDefinition,
    ModelArtifact,
    ModelDefinition,
    ModelVersionRecord,
    PredictionRecord,
)
from app.services.research_data.qlib_adapter import ADAPTER_VERSION, QlibAdapter, VersionResolver
from app.services.research_data.registry import ResearchRegistry

from .adapter import LightGBMModelAdapter, ModelTrainingError
from .artifact_store import (
    ModelArtifactStore,
    compute_config_digest,
    compute_model_artifact_id,
)
from .specs import ModelTrainSpec
from .version import MODEL_TRAINER_VERSION


def from_qlib_instrument(qlib_id: str) -> str:
    """sz000001 / sh600000 → CNStock:000001（研究层 instrument_key）。"""
    text = str(qlib_id or "").strip().lower()
    if text.startswith("sh") and len(text) >= 8:
        return f"CNStock:{text[2:]}"
    if text.startswith("sz") and len(text) >= 8:
        return f"CNStock:{text[2:]}"
    return f"UNKNOWN:{text}"


def _predictions_to_records(
    series: pd.Series,
    *,
    model_version: str,
    dataset_hash: str,
    bundle_hash: str,
) -> list[PredictionRecord]:
    """Qlib MultiIndex → PredictionRecord 列表。"""
    out: list[PredictionRecord] = []
    for idx, val in series.items():
        if isinstance(idx, tuple) and len(idx) >= 2:
            inst, dt = idx[0], idx[1]
        else:
            inst, dt = "UNKNOWN", idx
        if hasattr(dt, "date"):
            trading_date = dt.date().isoformat() if callable(getattr(dt, "date", None)) else str(dt)[:10]
        else:
            trading_date = str(dt)[:10]
        out.append(
            PredictionRecord(
                instrument_key=from_qlib_instrument(str(inst)),
                trading_date=trading_date,
                prediction=float(val),
                model_version=model_version,
                dataset_hash=dataset_hash,
                bundle_hash=bundle_hash,
            )
        )
    return out


def _predictions_parquet_bytes(records: list[PredictionRecord]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table(
        {
            "instrument_key": [r.instrument_key for r in records],
            "trading_date": [r.trading_date for r in records],
            "prediction": [r.prediction for r in records],
            "model_version": [r.model_version for r in records],
            "dataset_hash": [r.dataset_hash for r in records],
            "bundle_hash": [r.bundle_hash for r in records],
        }
    )
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


def _maybe_mlflow_log(
    *,
    experiment_name: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
) -> Optional[str]:
    """可选 MLflow；不可用时不阻塞。"""
    try:
        import mlflow
    except ImportError:
        return None
    try:
        mlflow.set_experiment(experiment_name)
        with mlflow.start_run() as run:
            for k, v in params.items():
                mlflow.log_param(k, v)
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    mlflow.log_metric(k, float(v))
            return run.info.run_id
    except Exception:
        return None


@dataclass
class ModelTrainResult:
    """训练产物摘要。"""

    artifact_id: str
    model_version_ref: str
    dataset_hash: str
    bundle_hash: str
    processor_version: str
    pipeline_digest: str
    metrics: dict[str, Any] = field(default_factory=dict)
    predictions: list[PredictionRecord] = field(default_factory=list)
    artifact_uri: str = ""
    experiment_id: str = ""
    mlflow_run_id: Optional[str] = None


class ModelTrainer:
    """组合 QlibAdapter + LightGBMModelAdapter + ArtifactStore。"""

    def __init__(
        self,
        qlib_adapter: QlibAdapter,
        registry: ResearchRegistry,
        *,
        artifact_store: ModelArtifactStore | None = None,
    ) -> None:
        self._adapter = qlib_adapter
        self._registry = registry
        self._store = artifact_store or ModelArtifactStore()
        self._lgb = LightGBMModelAdapter()
        self._versions = VersionResolver(
            qlib_adapter._query, registry  # noqa: SLF001 — 训练层需 bundle 身份
        )

    def _resolve_model(self, spec: ModelTrainSpec) -> ModelDefinition:
        if spec.model is not None:
            return spec.model
        if spec.model_ref:
            # Registry 仅存 ModelVersionRecord.config；ModelDefinition 从 ref + record 重建
            rec = self._registry.get_model_version(spec.model_ref)
            code, version = spec.model_ref.split("@", 1)
            try:
                base = self._registry.get_model(code)
                name = base.name
                engine = base.engine
            except KeyError:
                name = code
                engine = "lightgbm"
            return ModelDefinition(
                code=code,
                version=version,
                name=name,
                engine=engine,  # type: ignore[arg-type]
                config=dict(rec.config or {}),
            )
        raise ModelTrainingError("ModelTrainSpec requires model or model_ref")

    def train(self, spec: ModelTrainSpec) -> ModelTrainResult:
        """标准训练：fit(train) → valid metrics → predict(test) → persist。"""
        bundle = self._versions.resolve(spec.dataset_spec.dataset_ref)
        model_def = self._resolve_model(spec)
        merged_config = dict(model_def.config or {})
        merged_config.update(spec.config_override or {})
        merged_config["seed"] = spec.seed

        config_digest = compute_config_digest(merged_config)
        model_ref = spec.resolved_model_ref(model_def)
        artifact_id = compute_model_artifact_id(
            bundle_hash=bundle.bundle_hash,
            model_ref=model_ref,
            config_digest=config_digest,
            seed=spec.seed,
        )

        self._registry.upsert_model(model_def)
        dataset_h = self._adapter.build_dataset(spec.dataset_spec)

        lgb_model = self._lgb.create_model(merged_config)
        self._lgb.fit(lgb_model, dataset_h)
        metrics = self._lgb.evaluate_valid(lgb_model, dataset_h)
        pred_series = self._lgb.predict(lgb_model, dataset_h, segment="test")
        predictions = _predictions_to_records(
            pred_series,
            model_version=model_ref,
            dataset_hash=bundle.dataset_hash,
            bundle_hash=bundle.bundle_hash,
        )

        # test 日期 ⊆ test 段
        test_start = spec.dataset_spec.segments.test.start
        test_end = spec.dataset_spec.segments.test.end
        for rec in predictions:
            d = date.fromisoformat(rec.trading_date)
            if d < test_start or d > test_end:
                raise ModelTrainingError(
                    f"prediction date {d} outside test segment "
                    f"{test_start}..{test_end}"
                )

        metadata = {
            "artifact_id": artifact_id,
            "model_version": model_ref,
            "dataset_ref": spec.dataset_spec.dataset_ref,
            "dataset_hash": bundle.dataset_hash,
            "bundle_hash": bundle.bundle_hash,
            "processor_version": bundle.processor_version,
            "pipeline_digest": bundle.pipeline_digest,
            "snapshot_id": bundle.snapshot_id,
            "adapter_version": ADAPTER_VERSION,
            "model_trainer_version": MODEL_TRAINER_VERSION,
            "config": merged_config,
            "config_digest": config_digest,
            "seed": spec.seed,
            "segments": spec.dataset_spec.segments.canonical_dict(),
            "label": (
                spec.dataset_spec.label.model_dump(mode="json")
                if spec.dataset_spec.label
                else None
            ),
            "metrics": metrics,
        }

        model_bytes = self._lgb.save_booster_bytes(lgb_model)
        pred_bytes = _predictions_parquet_bytes(predictions) if predictions else None
        artifact_rec = self._store.write_bundle(
            artifact_id,
            model_bin=model_bytes,
            metadata=metadata,
            predictions_parquet=pred_bytes,
        )
        self._registry.upsert_artifact(artifact_rec)

        processor_ref = (
            bundle.processor_version
            if bundle.processor_version != "none"
            else None
        )
        self._registry.upsert_model_version(
            ModelVersionRecord(
                model_code=model_def.code,
                version=model_def.version,
                config=merged_config,
                artifact_id=artifact_id,
                metrics=metrics,
                dataset_ref=spec.dataset_spec.dataset_ref,
                processor_ref=processor_ref,
            )
        )

        experiment_id = f"exp_{artifact_id[:16]}"
        exp_params = dict(metadata)
        mlflow_run_id = _maybe_mlflow_log(
            experiment_name=spec.experiment_name,
            params={
                "dataset_hash": bundle.dataset_hash,
                "bundle_hash": bundle.bundle_hash,
                "model_version": model_ref,
                "artifact_id": artifact_id,
            },
            metrics=metrics,
        )
        self._registry.upsert_experiment(
            ExperimentDefinition(
                experiment_id=experiment_id,
                name=spec.experiment_name,
                dataset_ref=spec.dataset_spec.dataset_ref,
                snapshot_id=bundle.snapshot_id,
                dataset_hash=bundle.dataset_hash,
                model_version_ref=model_ref,
                mlflow_run_id=mlflow_run_id,
                parameters=exp_params,
            )
        )

        # 兼容已有 ModelArtifact 形状
        _ = ModelArtifact(
            model_code=model_def.code,
            version=model_def.version,
            engine=model_def.engine,
            dataset_ref=spec.dataset_spec.dataset_ref,
            processor_ref=processor_ref,
            artifact_uri=artifact_rec.storage_uri,
            metrics=metrics,
        )

        return ModelTrainResult(
            artifact_id=artifact_id,
            model_version_ref=model_ref,
            dataset_hash=bundle.dataset_hash,
            bundle_hash=bundle.bundle_hash,
            processor_version=bundle.processor_version,
            pipeline_digest=bundle.pipeline_digest,
            metrics=metrics,
            predictions=predictions,
            artifact_uri=artifact_rec.storage_uri,
            experiment_id=experiment_id,
            mlflow_run_id=mlflow_run_id,
        )
