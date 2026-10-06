"""Phase 4A：Factor Lab Foundation（研究侧 Feature 语义扩展）。

禁止导入交易侧 ``app.services.factors``。
"""

from .artifact_store import FactorDatasetArtifactStore
from .dataset import (
    FactorManifestError,
    build_factor_dataset_record,
    build_manifest,
    compute_factor_dataset_id,
    validate_manifest,
)
from .dependencies import (
    FactorDependencyError,
    parse_dependency,
    validate_dependencies,
    validate_for_backtest,
)
from .hash import compute_factor_hash
from .immutability import FeatureImmutabilityError, assert_feature_immutable, ensure_factor_hash
from .models import FactorDatasetManifest, FactorDependency, FactorSpec
from .registry_api import (
    get_factor,
    get_factor_dataset,
    is_backtest_eligible,
    register_factor,
    register_factor_dataset,
)
from .types import (
    DEPENDENCY_TYPES,
    SCHEMA_LONG,
    SCHEMA_WIDE,
    recommend_layout,
)
from .version import FACTOR_LAB_CONTRACT_VERSION
from .compute import (
    ComputePlan,
    FactorComputeService,
    FactorFrame,
    PITComputeContext,
    build_compute_plan,
    compute_result_dataset_hash,
    resolve_dependency_dag,
    select_engine,
)
from .evaluation import (
    EVALUATOR_VERSION,
    EvaluationFrame,
    EvaluationPlan,
    EvaluationResult,
    EvaluationSpec,
    FactorEvaluationService,
    ForwardReturnEngine,
    ReturnSpec,
    build_evaluation_plan,
    compute_evaluation_hash,
)
from .metrics import (
    METRIC_VERSION,
    FactorEvaluationSummary,
    FactorMetricsService,
    MetricSpec,
    MetricTimeSeries,
    compute_metric_hash,
)

__all__ = [
    "DEPENDENCY_TYPES",
    "EVALUATOR_VERSION",
    "FACTOR_LAB_CONTRACT_VERSION",
    "METRIC_VERSION",
    "SCHEMA_LONG",
    "SCHEMA_WIDE",
    "ComputePlan",
    "EvaluationFrame",
    "EvaluationPlan",
    "EvaluationResult",
    "EvaluationSpec",
    "FactorComputeService",
    "FactorDatasetArtifactStore",
    "FactorDatasetManifest",
    "FactorDependency",
    "FactorDependencyError",
    "FactorEvaluationService",
    "FactorEvaluationSummary",
    "FactorFrame",
    "FactorManifestError",
    "FactorMetricsService",
    "FeatureImmutabilityError",
    "FactorSpec",
    "ForwardReturnEngine",
    "MetricSpec",
    "MetricTimeSeries",
    "PITComputeContext",
    "ReturnSpec",
    "assert_feature_immutable",
    "build_compute_plan",
    "build_evaluation_plan",
    "build_factor_dataset_record",
    "build_manifest",
    "compute_evaluation_hash",
    "compute_factor_dataset_id",
    "compute_factor_hash",
    "compute_metric_hash",
    "compute_result_dataset_hash",
    "ensure_factor_hash",
    "get_factor",
    "get_factor_dataset",
    "is_backtest_eligible",
    "parse_dependency",
    "recommend_layout",
    "register_factor",
    "register_factor_dataset",
    "resolve_dependency_dag",
    "select_engine",
    "validate_dependencies",
    "validate_for_backtest",
    "validate_manifest",
]
