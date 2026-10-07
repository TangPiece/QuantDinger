"""Phase 9B — Feature / Factor Platform。"""

from .hashing import compute_factor_hash, compute_feature_set_hash
from .protocol import ENGINE_VERSION, FeatureSetManifest, FactorBuildResult
from .runner import FeatureFactorPlatformError, FeatureFactorService

__all__ = [
    "ENGINE_VERSION",
    "FeatureFactorPlatformError",
    "FeatureFactorService",
    "FeatureSetManifest",
    "FactorBuildResult",
    "compute_factor_hash",
    "compute_feature_set_hash",
]
