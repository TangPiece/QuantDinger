"""Phase 4H：Factor Combination。"""

from app.services.research_data.contracts import FactorCombinationSummary

from .hash import compute_combination_hash
from .orchestrator import (
    CombinationResult,
    FactorCombinationError,
    FactorCombinationService,
)
from .protocol import (
    COMBINATION_VERSION,
    CombinationSpec,
    WeightMethod,
    NormalizeMethod,
)
from .weighting import WeightSolverError

__all__ = [
    "COMBINATION_VERSION",
    "CombinationResult",
    "CombinationSpec",
    "FactorCombinationError",
    "FactorCombinationService",
    "FactorCombinationSummary",
    "NormalizeMethod",
    "WeightMethod",
    "WeightSolverError",
    "compute_combination_hash",
]
