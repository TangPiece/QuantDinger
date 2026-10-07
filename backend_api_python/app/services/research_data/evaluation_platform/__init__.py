"""Phase 9C — Factor Evaluation Platform。"""

from .hashing import compute_policy_content_hash, compute_run_content_hash
from .policy_presets import DEFAULT_EQUITY_FACTOR_V1, default_equity_factor_v1, get_policy
from .protocol import ENGINE_VERSION, EvaluationRun, FactorQualityScore
from .runner import FactorEvaluationPlatformError, FactorEvaluationPlatformService

__all__ = [
    "DEFAULT_EQUITY_FACTOR_V1",
    "ENGINE_VERSION",
    "EvaluationRun",
    "FactorEvaluationPlatformError",
    "FactorEvaluationPlatformService",
    "FactorQualityScore",
    "compute_policy_content_hash",
    "compute_run_content_hash",
    "default_equity_factor_v1",
    "get_policy",
]
