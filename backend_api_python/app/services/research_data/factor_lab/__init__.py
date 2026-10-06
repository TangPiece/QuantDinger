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

__all__ = [
    "DEPENDENCY_TYPES",
    "FACTOR_LAB_CONTRACT_VERSION",
    "SCHEMA_LONG",
    "SCHEMA_WIDE",
    "FactorDatasetArtifactStore",
    "FactorDatasetManifest",
    "FactorDependency",
    "FactorDependencyError",
    "FactorManifestError",
    "FeatureImmutabilityError",
    "FactorSpec",
    "assert_feature_immutable",
    "build_factor_dataset_record",
    "build_manifest",
    "compute_factor_dataset_id",
    "compute_factor_hash",
    "ensure_factor_hash",
    "get_factor",
    "get_factor_dataset",
    "is_backtest_eligible",
    "parse_dependency",
    "recommend_layout",
    "register_factor",
    "register_factor_dataset",
    "validate_dependencies",
    "validate_for_backtest",
    "validate_manifest",
]
