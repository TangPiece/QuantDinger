"""Phase 5F：Research → Production Bridge。"""

from app.services.research_data.contracts import (
    ProductionBundleSummary,
    ProductionDeploymentRunSummary,
    ProductionDeploymentSummary,
)

from .hash import compute_production_bundle_hash, normalize_production_bundle_spec
from .protocol import (
    ENGINE_VERSION,
    FeatureParityReport,
    GateResult,
    InferenceRequest,
    InferenceResponse,
    ProductionBundleSpec,
)
from .runner import BundleResult, ProductionBridgeError, ProductionBridgeService
from .state_machine import StateTransitionError

__all__ = [
    "ENGINE_VERSION",
    "BundleResult",
    "FeatureParityReport",
    "GateResult",
    "InferenceRequest",
    "InferenceResponse",
    "ProductionBridgeError",
    "ProductionBridgeService",
    "ProductionBundleSpec",
    "ProductionBundleSummary",
    "ProductionDeploymentRunSummary",
    "ProductionDeploymentSummary",
    "StateTransitionError",
    "compute_production_bundle_hash",
    "normalize_production_bundle_spec",
]
