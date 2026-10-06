"""Phase 4F：Factor Stability / Decay Evaluation。"""

from app.services.research_data.contracts import FactorStabilitySummary

from .hash import compute_stability_hash
from .orchestrator import FactorStabilityError, FactorStabilityService, StabilityResult
from .protocol import (
    STABILITY_VERSION,
    CostModelSpec,
    DecayPoint,
    GroupStabilityRow,
    ICDistribution,
    RegimeRow,
    RollingICRow,
    StabilityFrames,
    StabilityManifest,
    StabilitySpec,
)

__all__ = [
    "STABILITY_VERSION",
    "CostModelSpec",
    "DecayPoint",
    "FactorStabilityError",
    "FactorStabilityService",
    "FactorStabilitySummary",
    "GroupStabilityRow",
    "ICDistribution",
    "RegimeRow",
    "RollingICRow",
    "StabilityFrames",
    "StabilityManifest",
    "StabilityResult",
    "StabilitySpec",
    "compute_stability_hash",
]
