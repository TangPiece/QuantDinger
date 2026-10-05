"""Phase 2D：LightGBM 训练（Dataset → Processor → Model → Artifact → Prediction）。"""

from .adapter import LightGBMModelAdapter, lightgbm_runtime_available
from .artifact_store import ModelArtifactStore, compute_config_digest, compute_model_artifact_id
from .runner import ModelTrainResult, ModelTrainer
from .specs import ModelTrainSpec, default_lgb_config, builtin_lgb_baseline_model
from .version import MODEL_TRAINER_VERSION

__all__ = [
    "LightGBMModelAdapter",
    "lightgbm_runtime_available",
    "ModelArtifactStore",
    "ModelTrainResult",
    "ModelTrainer",
    "ModelTrainSpec",
    "MODEL_TRAINER_VERSION",
    "builtin_lgb_baseline_model",
    "compute_config_digest",
    "compute_model_artifact_id",
    "default_lgb_config",
]
