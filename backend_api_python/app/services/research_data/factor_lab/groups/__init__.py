"""Phase 4E：Group Return / Turnover / Cost-aware Evaluation。"""

from .aggregator import GroupEvaluationAggregator
from .artifact_store import GroupArtifactStore
from .assigner import GroupAssigner
from .cost import CostCalculator
from .hash import compute_group_evaluation_hash
from .orchestrator import (
    FactorGroupEvaluationError,
    FactorGroupEvaluationService,
    GroupEvaluationResult,
)
from .protocol import (
    GROUP_VERSION,
    CostModelSpec,
    GroupEvaluationSummary,
    GroupFrames,
    GroupSpec,
)
from .returns import GroupReturnCalculator
from .turnover import TurnoverCalculator

__all__ = [
    "GROUP_VERSION",
    "CostCalculator",
    "CostModelSpec",
    "FactorGroupEvaluationError",
    "FactorGroupEvaluationService",
    "GroupAssigner",
    "GroupArtifactStore",
    "GroupEvaluationAggregator",
    "GroupEvaluationResult",
    "GroupEvaluationSummary",
    "GroupFrames",
    "GroupReturnCalculator",
    "GroupSpec",
    "TurnoverCalculator",
    "compute_group_evaluation_hash",
]
