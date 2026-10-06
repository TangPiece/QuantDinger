"""Phase 3E：Dual Engine Consistency。"""

from .artifact_store import ConsistencyArtifactStore, compute_run_id
from .diff import KNOWN_DIFF_REASONS
from .fingerprint import compute_semantic_fingerprint
from .levels import LEVEL_ORDER, policies_for_level
from .models import (
    ConsistencyAttribution,
    ConsistencyDiff,
    ConsistencyReport,
    ConsistencyScenario,
)
from .runner import ConsistencyEngine, ConsistencyError
from .signal_check import SignalCheckResult, check_signal_artifact
from .version import CONSISTENCY_ENGINE_VERSION

__all__ = [
    "CONSISTENCY_ENGINE_VERSION",
    "KNOWN_DIFF_REASONS",
    "LEVEL_ORDER",
    "ConsistencyArtifactStore",
    "ConsistencyAttribution",
    "ConsistencyDiff",
    "ConsistencyEngine",
    "ConsistencyError",
    "ConsistencyReport",
    "ConsistencyScenario",
    "SignalCheckResult",
    "check_signal_artifact",
    "compute_run_id",
    "compute_semantic_fingerprint",
    "policies_for_level",
]
