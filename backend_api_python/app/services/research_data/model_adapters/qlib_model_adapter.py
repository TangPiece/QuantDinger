"""QlibModelAdapter：TrainingContext → Phase 2D ModelTrainer（Qlib 不泄漏）。"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.services.research_data.contracts import ModelDefinition
from app.services.research_data.model_training import (
    ModelArtifactStore as TrainArtifactStore,
    ModelTrainSpec,
    ModelTrainer,
    lightgbm_runtime_available,
)
from app.services.research_data.model_training.adapter import ModelTrainingError
from app.services.research_data.qlib_adapter import (
    QlibAdapter,
    ResearchDatasetSpec,
    SegmentRange,
    SegmentSpec,
)
from app.services.research_data.registry import ResearchRegistry

from .config_map import map_training_config_to_lgb
from .errors import ModelAdapterError, map_exception
from .protocol import (
    ADAPTER_ENGINE_VERSION,
    ModelArtifactCandidate,
    PredictionRequest,
    PredictionResult,
    PredictionRow,
    TrainingContext,
)


def _parse_date(text: str, *, fallback: date | None = None) -> date:
    raw = (text or "").strip()
    if not raw:
        if fallback is not None:
            return fallback
        raise ModelAdapterError(
            "segment date missing",
            failure_class="CONFIG_ERROR",
            stage="PREPARING",
        )
    return date.fromisoformat(raw[:10])


def segments_from_context(ctx: TrainingContext) -> SegmentSpec:
    seg = ctx.segments
    train_start = _parse_date(seg.train_start)
    train_end = _parse_date(seg.train_end)
    valid_start = _parse_date(seg.validation_start)
    valid_end = _parse_date(seg.validation_end)
    # test：显式或 valid_end 之后一天到 train 窗口外推
    if seg.test_start and seg.test_end:
        test_start = _parse_date(seg.test_start)
        test_end = _parse_date(seg.test_end)
    else:
        # 默认：valid 结束后紧接短 test（fixture 友好）
        from datetime import timedelta

        test_start = valid_end + timedelta(days=1)
        test_end = _parse_date(seg.test_end, fallback=test_start + timedelta(days=30))
    return SegmentSpec(
        train=SegmentRange(start=train_start, end=train_end),
        valid=SegmentRange(start=valid_start, end=valid_end),
        test=SegmentRange(start=test_start, end=test_end),
    )


class QlibModelAdapter:
    """Qlib/LightGBM 执行适配器；Domain 只见 Candidate / PredictionResult。"""

    name = "qlib_lightgbm"

    def __init__(
        self,
        *,
        qlib_adapter: QlibAdapter | None = None,
        research_registry: ResearchRegistry | None = None,
        artifact_store: TrainArtifactStore | None = None,
        trainer: ModelTrainer | None = None,
    ) -> None:
        self._qlib = qlib_adapter
        self._registry = research_registry
        self._store = artifact_store
        self._trainer = trainer

    def _require_deps(self) -> tuple[QlibAdapter, ResearchRegistry, ModelTrainer]:
        if self._trainer is not None and self._qlib is not None and self._registry is not None:
            return self._qlib, self._registry, self._trainer
        if self._qlib is None or self._registry is None:
            raise ModelAdapterError(
                "QlibModelAdapter requires qlib_adapter and research_registry",
                failure_class="RESOURCE_ERROR",
                stage="PREPARING",
            )
        if not lightgbm_runtime_available():
            raise ModelAdapterError(
                "lightgbm runtime unavailable",
                failure_class="RESOURCE_ERROR",
                stage="PREPARING",
            )
        store = self._store or TrainArtifactStore()
        trainer = self._trainer or ModelTrainer(
            self._qlib, self._registry, artifact_store=store
        )
        self._store = store
        self._trainer = trainer
        return self._qlib, self._registry, trainer

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "adapter_version": ADAPTER_ENGINE_VERSION,
            "framework": "LIGHTGBM",
            "engine": "qlib",
        }

    def validate_config(self, ctx: TrainingContext) -> None:
        if not (ctx.dataset_ref or "").strip():
            raise ModelAdapterError(
                "dataset_ref required",
                failure_class="CONFIG_ERROR",
                stage="PREPARING",
            )
        if not (ctx.segments.train_start and ctx.segments.train_end):
            raise ModelAdapterError(
                "train segment dates required",
                failure_class="CONFIG_ERROR",
                stage="PREPARING",
            )
        if not (ctx.segments.validation_start and ctx.segments.validation_end):
            raise ModelAdapterError(
                "validation segment dates required",
                failure_class="CONFIG_ERROR",
                stage="PREPARING",
            )
        try:
            segments_from_context(ctx)
            map_training_config_to_lgb(
                ctx.config,
                hyperparameters=ctx.hyperparameters,
                seed=ctx.random_seed,
            )
        except ModelAdapterError:
            raise
        except Exception as exc:
            raise map_exception(exc, stage="PREPARING") from exc

    def prepare(self, ctx: TrainingContext) -> None:
        self.validate_config(ctx)
        qlib, _reg, _trainer = self._require_deps()
        try:
            identity = qlib.resolve(ctx.dataset_ref)
            qlib.ensure_cache(ctx.dataset_ref)
            dh = getattr(identity, "dataset_hash", "") or ""
            if ctx.dataset_hash and dh and dh != ctx.dataset_hash:
                raise ModelAdapterError(
                    f"dataset_hash mismatch: run={ctx.dataset_hash} resolved={dh}",
                    failure_class="DATA_MISSING",
                    stage="PREPARING",
                )
        except ModelAdapterError:
            raise
        except Exception as exc:
            raise map_exception(exc, stage="PREPARING") from exc

    def _to_train_spec(self, ctx: TrainingContext) -> ModelTrainSpec:
        segments = segments_from_context(ctx)
        lgb_cfg = map_training_config_to_lgb(
            ctx.config,
            hyperparameters=ctx.hyperparameters,
            seed=ctx.random_seed,
        )
        model = ModelDefinition(
            code=(ctx.metadata.get("model_code") or "qd_platform_lgb"),
            version=str(ctx.metadata.get("model_version") or "1"),
            name="phase9f4_qlib",
            engine="lightgbm",
            config=lgb_cfg,
        )
        return ModelTrainSpec(
            dataset_spec=ResearchDatasetSpec(
                dataset_ref=ctx.dataset_ref,
                segments=segments,
            ),
            model=model,
            seed=int(ctx.random_seed or 42),
            experiment_name=ctx.runtime.experiment_name or "phase9f4_train",
            config_override={},
        )

    def train(self, ctx: TrainingContext) -> ModelArtifactCandidate:
        self.prepare(ctx)
        _qlib, _reg, trainer = self._require_deps()
        try:
            spec = self._to_train_spec(ctx)
            result = trainer.train(spec)
        except ModelAdapterError:
            raise
        except ModelTrainingError as exc:
            raise map_exception(exc, stage="RUNNING") from exc
        except Exception as exc:
            raise map_exception(exc, stage="RUNNING") from exc

        uri = result.artifact_uri or ""
        bin_path = Path(uri) / "model.bin" if uri else None
        if bin_path and bin_path.is_file():
            raw = bin_path.read_bytes()
            checksum = hashlib.sha256(raw).hexdigest()
            file_size = len(raw)
            artifact_uri = str(bin_path.resolve())
        else:
            # fallback：用 artifact_id 定位
            store = self._store or TrainArtifactStore()
            dest = store.dir_for(result.artifact_id)
            bin_path = dest / "model.bin"
            if not bin_path.is_file():
                raise ModelAdapterError(
                    f"model.bin missing after train: {bin_path}",
                    failure_class="ARTIFACT_ERROR",
                    stage="FINALIZING",
                )
            raw = bin_path.read_bytes()
            checksum = hashlib.sha256(raw).hexdigest()
            file_size = len(raw)
            artifact_uri = str(bin_path.resolve())

        return ModelArtifactCandidate(
            artifact_uri=artifact_uri,
            checksum=checksum,
            file_size=file_size,
            framework="LIGHTGBM",
            framework_version=ctx.framework_version or "",
            model_metadata={
                "trainer_artifact_id": result.artifact_id,
                "model_version_ref": result.model_version_ref,
                "dataset_hash": result.dataset_hash,
                "bundle_hash": result.bundle_hash,
                "processor_version": result.processor_version,
                "pipeline_digest": result.pipeline_digest,
                "prediction_count": len(result.predictions),
                "qlib_recorder_uri": result.experiment_id or "",
            },
            metrics=dict(result.metrics or {}),
            trainer_artifact_id=result.artifact_id,
        )

    def evaluate(
        self, ctx: TrainingContext, candidate: ModelArtifactCandidate
    ) -> dict[str, Any]:
        return dict(candidate.metrics or {})

    def save_artifact(
        self,
        ctx: TrainingContext,
        payload: bytes,
        metadata: dict[str, Any],
    ) -> ModelArtifactCandidate:
        store = self._store or TrainArtifactStore(
            root=Path(ctx.runtime.artifact_root) if ctx.runtime.artifact_root else None
        )
        artifact_id = hashlib.sha256(
            f"{ctx.training_run_id}|{ctx.dataset_hash}".encode("utf-8")
        ).hexdigest()
        try:
            rec = store.write_bundle(
                artifact_id,
                model_bin=payload,
                metadata=dict(metadata or {}),
            )
        except Exception as exc:
            raise map_exception(exc, stage="FINALIZING") from exc
        checksum = hashlib.sha256(payload).hexdigest()
        return ModelArtifactCandidate(
            artifact_uri=str((store.dir_for(artifact_id) / "model.bin").resolve()),
            checksum=checksum,
            file_size=len(payload),
            framework="LIGHTGBM",
            model_metadata={"trainer_artifact_id": artifact_id, **dict(metadata or {})},
            trainer_artifact_id=artifact_id,
        )

    def load_artifact(self, artifact_uri: str) -> bytes:
        path = Path(artifact_uri)
        if path.is_dir():
            path = path / "model.bin"
        if not path.is_file():
            raise ModelAdapterError(
                f"artifact not found: {artifact_uri}",
                failure_class="ARTIFACT_ERROR",
                stage="RUNNING",
            )
        return path.read_bytes()

    def predict(self, request: PredictionRequest) -> PredictionResult:
        qlib, _reg, trainer = self._require_deps()
        if not (request.dataset_ref or "").strip():
            raise ModelAdapterError(
                "PredictionRequest.dataset_ref required",
                failure_class="CONFIG_ERROR",
                stage="RUNNING",
            )
        if not (request.artifact_uri or "").strip():
            raise ModelAdapterError(
                "PredictionRequest.artifact_uri required",
                failure_class="ARTIFACT_ERROR",
                stage="RUNNING",
            )
        try:
            from app.services.research_data.model_training.adapter import LightGBMModelAdapter

            # 用短 train 路径：load booster + build dataset + predict test
            ctx_segments = request.segments
            # 构造最小 TrainingContext 仅用于 segments
            from .protocol import TrainingContext as TC
            from .protocol import TrainingSegments

            tmp = TC(
                training_run_id="predict",
                dataset_ref=request.dataset_ref,
                dataset_hash=request.dataset_hash,
                segments=ctx_segments or TrainingSegments(),
            )
            if not tmp.segments.train_start:
                raise ModelAdapterError(
                    "segments required for predict",
                    failure_class="CONFIG_ERROR",
                    stage="RUNNING",
                )
            segments = segments_from_context(tmp)
            dataset_h = qlib.build_dataset(
                ResearchDatasetSpec(
                    dataset_ref=request.dataset_ref,
                    segments=segments,
                )
            )
            raw = self.load_artifact(request.artifact_uri)
            import tempfile

            import lightgbm as lgb

            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmpf:
                tmp_path = Path(tmpf.name)
                tmp_path.write_bytes(raw)
            try:
                booster = lgb.Booster(model_file=str(tmp_path))
            finally:
                tmp_path.unlink(missing_ok=True)

            # 挂到假 LGBModel 外壳以复用 predict 映射成本高；直接 prepare+predict
            from qlib.data.dataset.handler import DataHandlerLP

            df = dataset_h.prepare(
                "test",
                col_set=["feature"],
                data_key=DataHandlerLP.DK_I,
            )
            if df is None or len(df) == 0:
                return PredictionResult(
                    model_version_id=request.model_version_id,
                    prediction_time=request.prediction_time
                    or datetime.now(timezone.utc).isoformat(),
                    rows=[],
                    metadata={"empty": True},
                )
            x = df["feature"] if "feature" in df.columns or hasattr(df, "columns") else df
            if hasattr(x, "values"):
                preds = booster.predict(x.values)
            else:
                preds = booster.predict(x)
            rows: list[PredictionRow] = []
            for idx, val in zip(df.index, preds):
                inst, dt = idx[0], idx[1] if isinstance(idx, tuple) and len(idx) >= 2 else ("?", idx)
                # 粗映射
                from app.services.research_data.model_training.runner import (
                    _trading_date_str,
                    from_qlib_instrument,
                    _split_pred_index,
                )

                inst2, dt2 = _split_pred_index(idx)
                rows.append(
                    PredictionRow(
                        instrument=from_qlib_instrument(str(inst2)),
                        prediction=float(val),
                        trading_date=_trading_date_str(dt2),
                    )
                )
            _ = LightGBMModelAdapter  # noqa: F841 — 文档边界：predict 仍经 QD 层
            _ = trainer
            return PredictionResult(
                model_version_id=request.model_version_id,
                prediction_time=request.prediction_time
                or datetime.now(timezone.utc).isoformat(),
                rows=rows,
                metadata={"n": len(rows)},
            )
        except ModelAdapterError:
            raise
        except Exception as exc:
            raise map_exception(exc, stage="RUNNING") from exc


__all__ = ["QlibModelAdapter", "segments_from_context", "lightgbm_runtime_available"]
