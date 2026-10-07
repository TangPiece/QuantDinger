"""Phase 9F-4：Model Adapter 合同（无 Qlib 类型泄漏）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

ADAPTER_ENGINE_VERSION = "qd_model_adapter@1"


class _AdapterModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TrainingSegments(_AdapterModel):
    train_start: str = ""
    train_end: str = ""
    validation_start: str = ""
    validation_end: str = ""
    test_start: str = ""
    test_end: str = ""


class TrainingRuntime(_AdapterModel):
    artifact_root: str = ""
    sidecar_root: str = ""
    experiment_name: str = "phase9f4_train"


class TrainingContext(_AdapterModel):
    """标准化 Adapter 输入（无 DatasetH / LGBModel）。"""

    training_run_id: str
    dataset_ref: str
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_id: str = ""
    feature_set_hash: str = ""
    label_hash: str = ""
    processor_version: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    random_seed: int = 42
    framework: str = "LIGHTGBM"
    framework_version: str = ""
    segments: TrainingSegments = Field(default_factory=TrainingSegments)
    resource: dict[str, Any] = Field(default_factory=dict)
    runtime: TrainingRuntime = Field(default_factory=TrainingRuntime)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelArtifactCandidate(_AdapterModel):
    """Adapter 产出；由 Training Service 登记为 ModelArtifact。"""

    artifact_uri: str
    checksum: str
    file_size: int = 0
    framework: str = "LIGHTGBM"
    framework_version: str = ""
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    adapter_version: str = ADAPTER_ENGINE_VERSION
    trainer_artifact_id: str = ""


class PredictionRequest(_AdapterModel):
    model_version_id: str = ""
    artifact_uri: str = ""
    dataset_ref: str = ""
    dataset_hash: str = ""
    feature_schema_hash: str = ""
    prediction_time: str = ""
    segments: TrainingSegments = Field(default_factory=TrainingSegments)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PredictionRow(_AdapterModel):
    instrument: str
    prediction: float
    trading_date: str = ""


class PredictionResult(_AdapterModel):
    model_version_id: str = ""
    prediction_time: str = ""
    rows: list[PredictionRow] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ModelAdapter(Protocol):
    """统一训练引擎门面。"""

    name: str

    def validate_config(self, ctx: TrainingContext) -> None: ...

    def prepare(self, ctx: TrainingContext) -> None: ...

    def train(self, ctx: TrainingContext) -> ModelArtifactCandidate: ...

    def predict(self, request: PredictionRequest) -> PredictionResult: ...

    def evaluate(self, ctx: TrainingContext, candidate: ModelArtifactCandidate) -> dict[str, Any]: ...

    def save_artifact(self, ctx: TrainingContext, payload: bytes, metadata: dict[str, Any]) -> ModelArtifactCandidate: ...

    def load_artifact(self, artifact_uri: str) -> bytes: ...

    def metadata(self) -> dict[str, Any]: ...


__all__ = [
    "ADAPTER_ENGINE_VERSION",
    "ModelAdapter",
    "ModelArtifactCandidate",
    "PredictionRequest",
    "PredictionResult",
    "PredictionRow",
    "TrainingContext",
    "TrainingRuntime",
    "TrainingSegments",
]
