"""Phase 4C：Factor Evaluation Foundation。"""

from .artifact_store import EvaluationArtifactStore, validate_evaluation_manifest
from .forward_return import ForwardReturnEngine, shift_trading_day
from .hash import compute_evaluation_hash
from .orchestrator import EvaluationResult, FactorEvaluationError, FactorEvaluationService
from .planner import EvaluationPlanError, build_evaluation_plan
from .protocol import (
    CALENDAR_VERSION,
    EVALUATOR_VERSION,
    SCHEMA_EVALUATION,
    EvaluationFrame,
    EvaluationManifest,
    EvaluationMode,
    EvaluationPlan,
    EvaluationSpec,
    ReturnSpec,
    SampleStatus,
)

__all__ = [
    "CALENDAR_VERSION",
    "EVALUATOR_VERSION",
    "SCHEMA_EVALUATION",
    "EvaluationArtifactStore",
    "EvaluationFrame",
    "EvaluationManifest",
    "EvaluationMode",
    "EvaluationPlan",
    "EvaluationPlanError",
    "EvaluationResult",
    "EvaluationSpec",
    "FactorEvaluationError",
    "FactorEvaluationService",
    "ForwardReturnEngine",
    "ReturnSpec",
    "SampleStatus",
    "build_evaluation_plan",
    "compute_evaluation_hash",
    "shift_trading_day",
    "validate_evaluation_manifest",
]
