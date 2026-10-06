"""Phase 4B：Factor Computation Engine。"""

from .hash import compute_plan_hash, compute_result_dataset_hash
from .orchestrator import ComputeResult, FactorComputeError, FactorComputeService
from .planner import ComputePlanError, build_compute_plan, select_engine
from .protocol import ComputePlan, FactorFrame, PITComputeContext
from .resolver import DependencyDAG, resolve_dependency_dag
from .writers import FactorDatasetWriter

__all__ = [
    "ComputePlan",
    "ComputePlanError",
    "ComputeResult",
    "DependencyDAG",
    "FactorComputeError",
    "FactorComputeService",
    "FactorDatasetWriter",
    "FactorFrame",
    "PITComputeContext",
    "build_compute_plan",
    "compute_plan_hash",
    "compute_result_dataset_hash",
    "resolve_dependency_dag",
    "select_engine",
]
