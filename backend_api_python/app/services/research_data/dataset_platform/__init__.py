"""Phase 9A — Research Dataset Platform（manifest + builder + immutability）。"""

from .hashing import compute_domain_dataset_hash
from .protocol import ENGINE_VERSION, DatasetManifest
from .runner import DatasetPlatformError, ResearchDatasetService

__all__ = [
    "ENGINE_VERSION",
    "DatasetManifest",
    "DatasetPlatformError",
    "ResearchDatasetService",
    "compute_domain_dataset_hash",
]
