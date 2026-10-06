"""Phase 5E：Qlib ↔ QuantDinger Cross Validation。"""

from app.services.research_data.contracts import CrossValidationSummary

from .hash import compute_cv_hash, normalize_cv_spec
from .protocol import (
    ENGINE_VERSION,
    AttributionBreakdown,
    CrossValidationReport,
    CrossValidationSpec,
    LayerResult,
    Tolerances,
)
from .runner import CrossValidationError, CrossValidationResult, CrossValidationService

__all__ = [
    "ENGINE_VERSION",
    "AttributionBreakdown",
    "CrossValidationError",
    "CrossValidationReport",
    "CrossValidationResult",
    "CrossValidationService",
    "CrossValidationSpec",
    "CrossValidationSummary",
    "LayerResult",
    "Tolerances",
    "compute_cv_hash",
    "normalize_cv_spec",
]
