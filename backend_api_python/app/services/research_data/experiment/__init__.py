"""Phase 2F：Experiment 顶层编排与复现。"""

from .compare import is_reproducible
from .fingerprint import (
    compute_repro_fingerprint,
    experiment_id_from_fingerprint,
)
from .manifest_store import ExperimentManifestStore
from .metrics import merge_experiment_metrics, signal_counts
from .mlflow_bridge import log_experiment_run
from .runner import ExperimentResult, ExperimentRunner
from .specs import ExperimentSpec
from .version import EXPERIMENT_PIPELINE_VERSION

__all__ = [
    "EXPERIMENT_PIPELINE_VERSION",
    "ExperimentManifestStore",
    "ExperimentResult",
    "ExperimentRunner",
    "ExperimentSpec",
    "compute_repro_fingerprint",
    "experiment_id_from_fingerprint",
    "is_reproducible",
    "log_experiment_run",
    "merge_experiment_metrics",
    "signal_counts",
]
