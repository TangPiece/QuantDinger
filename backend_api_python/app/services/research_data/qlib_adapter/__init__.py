"""Qlib Adapter Core：QuantDinger Domain → Qlib API 边界。

业务代码经本包访问 Qlib；禁止散落 qlib.init。
"""

from .dataset_adapter import DatasetAdapter, QlibAdapter
from .dataset_cache import DatasetArtifactCache, compute_dataset_artifact_id, dataset_cache_root
from .errors import (
    QlibAdapterError,
    QlibRuntimeError,
    UnsupportedFeatureError,
    UnsupportedProcessorError,
    VersionResolveError,
)
from .feature_adapter import CompiledFeature, FeatureAdapter
from .handler import HandlerBuilder, QuantDingerQLibHandler
from .label_adapter import CompiledLabel, LabelAdapter
from .processor_adapter import (
    ProcessorAdapter,
    builtin_cs_zscore_processor,
    builtin_identity_processor,
)
from .runtime import QlibRuntime, default_runtime
from .specs import (
    ResearchDatasetSpec,
    SegmentRange,
    SegmentSpec,
    default_fwd_ret_label,
)
from .version import ADAPTER_VERSION
from .version_resolver import ResearchBundleIdentity, VersionResolver, compute_bundle_hash

__all__ = [
    "ADAPTER_VERSION",
    "CompiledFeature",
    "CompiledLabel",
    "DatasetAdapter",
    "DatasetArtifactCache",
    "FeatureAdapter",
    "HandlerBuilder",
    "LabelAdapter",
    "ProcessorAdapter",
    "QlibAdapter",
    "QlibAdapterError",
    "QlibRuntime",
    "QlibRuntimeError",
    "QuantDingerQLibHandler",
    "ResearchBundleIdentity",
    "ResearchDatasetSpec",
    "SegmentRange",
    "SegmentSpec",
    "UnsupportedFeatureError",
    "UnsupportedProcessorError",
    "VersionResolveError",
    "VersionResolver",
    "builtin_cs_zscore_processor",
    "builtin_identity_processor",
    "compute_bundle_hash",
    "compute_dataset_artifact_id",
    "dataset_cache_root",
    "default_fwd_ret_label",
    "default_runtime",
]
