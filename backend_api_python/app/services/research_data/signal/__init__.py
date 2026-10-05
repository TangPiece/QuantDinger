"""Phase 2E：Prediction → Signal → TargetPosition（不下单）。"""

from .artifact_store import (
    SignalArtifactStore,
    compute_signal_artifact_id,
)
from .order_intent_mapper import order_intents_from_targets
from .portfolio import EqualWeightPortfolio
from .predictions import (
    compute_prediction_id,
    normalize_prediction,
    normalize_predictions,
    prediction_fingerprint,
)
from .runner import SignalPipeline, SignalPipelineResult
from .specs import SignalRunSpec
from .strategies import ThresholdStrategy, TopKStrategy
from .timeutil import resolve_signal_times
from .version import SIGNAL_PIPELINE_VERSION

__all__ = [
    "SIGNAL_PIPELINE_VERSION",
    "EqualWeightPortfolio",
    "SignalArtifactStore",
    "SignalPipeline",
    "SignalPipelineResult",
    "SignalRunSpec",
    "ThresholdStrategy",
    "TopKStrategy",
    "compute_prediction_id",
    "compute_signal_artifact_id",
    "normalize_prediction",
    "normalize_predictions",
    "order_intents_from_targets",
    "prediction_fingerprint",
    "resolve_signal_times",
]
