"""Phase 4G：Factor Neutralization。"""

from app.services.research_data.contracts import FactorNeutralizationSummary

from .exposure import (
    ExposureProvider,
    ExposureProviderError,
    InjectedExposureProvider,
)
from .hash import compute_neutralization_hash
from .orchestrator import (
    FactorNeutralizationError,
    FactorNeutralizationService,
    NeutralizationResult,
)
from .protocol import (
    NEUTRALIZATION_VERSION,
    ExposureDiagnostic,
    ExposureRow,
    NeutralizationSpec,
    NeutralizedFactorRow,
)

__all__ = [
    "NEUTRALIZATION_VERSION",
    "ExposureDiagnostic",
    "ExposureProvider",
    "ExposureProviderError",
    "ExposureRow",
    "FactorNeutralizationError",
    "FactorNeutralizationService",
    "FactorNeutralizationSummary",
    "InjectedExposureProvider",
    "NeutralizationResult",
    "NeutralizationSpec",
    "NeutralizedFactorRow",
    "compute_neutralization_hash",
]
