"""Phase 9F-4：Model Adapter 合同与 QlibModelAdapter。"""

from .config_map import map_training_config_to_lgb
from .errors import ModelAdapterError, map_exception
from .protocol import (
    ADAPTER_ENGINE_VERSION,
    ModelAdapter,
    ModelArtifactCandidate,
    PredictionRequest,
    PredictionResult,
    PredictionRow,
    TrainingContext,
    TrainingRuntime,
    TrainingSegments,
)
from .qlib_model_adapter import QlibModelAdapter, lightgbm_runtime_available
from .registry import ModelAdapterRegistry, default_adapter_registry

__all__ = [
    "ADAPTER_ENGINE_VERSION",
    "ModelAdapter",
    "ModelAdapterError",
    "ModelAdapterRegistry",
    "ModelArtifactCandidate",
    "PredictionRequest",
    "PredictionResult",
    "PredictionRow",
    "QlibModelAdapter",
    "TrainingContext",
    "TrainingRuntime",
    "TrainingSegments",
    "default_adapter_registry",
    "lightgbm_runtime_available",
    "map_exception",
    "map_training_config_to_lgb",
]
