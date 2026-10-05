"""ModelTrainer：DatasetH → LightGBM fit/eval/predict → Artifact + Registry。"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import pandas as pd

from app.services.research_data.contracts import (
    ModelArtifact,
    ModelDefinition,
    ModelVersionRecord,
    PredictionRecord,
)
from app.services.research_data.qlib_adapter import ADAPTER_VERSION, QlibAdapter, VersionResolver
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.signal.predictions import compute_prediction_id

from .adapter import LightGBMModelAdapter, ModelTrainingError
from .artifact_store import (
    ModelArtifactStore,
    compute_config_digest,
    compute_model_artifact_id,
)
from .specs import ModelTrainSpec
from .version import MODEL_TRAINER_VERSION


def _end_qlib_recorder() -> None:
    """结束 Qlib Recorder，避免后续 qlib.init 因 Recorder 仍激活而失败。"""
    try:
        from qlib.workflow import R

        R.end_exp()
    except Exception:
        pass


def from_qlib_instrument(qlib_id: str) -> str:
    """sz000001 / sh600000 → CNStock:000001（研究层 instrument_key）。"""
    text = str(qlib_id or "").strip().lower()
    if text.startswith("sh") and len(text) >= 8:
        return f"CNStock:{text[2:]}"
    if text.startswith("sz") and len(text) >= 8:
        return f"CNStock:{text[2:]}"
    return f"UNKNOWN:{text}"


def _split_pred_index(idx: Any) -> tuple[Any, Any]:
    """从 Qlib MultiIndex 拆出 (instrument, datetime)。"""
    if not (isinstance(idx, tuple) and len(idx) >= 2):
        return "UNKNOWN", idx
    a, b = idx[0], idx[1]
    # 优先使用 pandas Timestamp / datetime
    if hasattr(a, "year") and not hasattr(b, "year"):
        return b, a
    if hasattr(b, "year") and not hasattr(a, "year"):
        return a, b
    a_s, b_s = str(a).lower(), str(b).lower()
    # instrument 形如 sh600000 / sz000001（不以日期开头）
    if len(a_s) >= 8 and a_s[:2] in ("sh", "sz") and a_s[2:8].isdigit():
        return a, b
    if len(b_s) >= 8 and b_s[:2] in ("sh", "sz") and b_s[2:8].isdigit():
        return b, a
    if ":" in a_s and not a_s[:4].isdigit():
        return a, b
    return a, b


def _trading_date_str(dt: Any) -> str:
    if hasattr(dt, "date") and callable(getattr(dt, "date", None)):
        try:
            return dt.date().isoformat()
        except Exception:
            pass
    text = str(dt)
    # 截取 YYYY-MM-DD
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text[:10]


def _predictions_to_records(
    series: pd.Series,
    *,
    model_version: str,
    dataset_hash: str,
    bundle_hash: str,
    snapshot_id: str = "",
) -> list[PredictionRecord]:
    """Qlib MultiIndex → PredictionRecord 列表（含 prediction_id / snapshot_id）。"""
    out: list[PredictionRecord] = []
    for idx, val in series.items():
        inst, dt = _split_pred_index(idx)
        instrument_key = from_qlib_instrument(str(inst))
        trading_date = _trading_date_str(dt)
        pred_id = compute_prediction_id(
            model_version=model_version,
            instrument_key=instrument_key,
            trading_date=trading_date,
            dataset_hash=dataset_hash,
        )
        out.append(
            PredictionRecord(
                instrument_key=instrument_key,
                trading_date=trading_date,
                prediction=float(val),
                model_version=model_version,
                dataset_hash=dataset_hash,
                bundle_hash=bundle_hash,
                prediction_id=pred_id,
                snapshot_id=snapshot_id or "",
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
            "prediction_id": [r.prediction_id for r in records],
            "snapshot_id": [r.snapshot_id for r in records],
        }
    )
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


@dataclass
class ModelTrainResult:
    """训练产物摘要（Experiment 登记由 Phase 2F ExperimentRunner 负责）。"""

    artifact_id: str
    model_version_ref: str
    dataset_hash: str
    bundle_hash: str
    processor_version: str
    pipeline_digest: str
    metrics: dict[str, Any] = field(default_factory=dict)
    predictions: list[PredictionRecord] = field(default_factory=list)
    artifact_uri: str = ""
    # 兼容旧字段；正式 experiment_id / mlflow 由 ExperimentRunner 写入
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
            snapshot_id=bundle.snapshot_id,
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

        # 兼容已有 ModelArtifact 形状（Experiment 登记见 ExperimentRunner）
        _ = ModelArtifact(
            model_code=model_def.code,
            version=model_def.version,
            engine=model_def.engine,
            dataset_ref=spec.dataset_spec.dataset_ref,
            processor_ref=processor_ref,
            artifact_uri=artifact_rec.storage_uri,
            metrics=metrics,
        )

        # LGB fit 会激活 Qlib Recorder；结束以免下一次 qlib.init 报错
        _end_qlib_recorder()

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
        )
