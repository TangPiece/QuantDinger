"""Qlib Adapter Core：QuantDinger Domain → Qlib API 边界。

业务代码经本包访问 Qlib；禁止散落 qlib.init。
"""

from .dataset_adapter import DatasetAdapter, QlibAdapter
from .errors import (
    QlibAdapterError,
    QlibRuntimeError,
    UnsupportedFeatureError,
    UnsupportedProcessorError,
    VersionResolveError,
)
from .feature_adapter import CompiledFeature, FeatureAdapter
from .processor_adapter import (
    ProcessorAdapter,
    builtin_cs_zscore_processor,
    builtin_identity_processor,
)
from .runtime import QlibRuntime, default_runtime
from .version import ADAPTER_VERSION
from .version_resolver import ResearchBundleIdentity, VersionResolver, compute_bundle_hash

__all__ = [
    "ADAPTER_VERSION",
    "CompiledFeature",
    "DatasetAdapter",
    "FeatureAdapter",
    "ProcessorAdapter",
    "QlibAdapter",
    "QlibAdapterError",
    "QlibRuntime",
    "QlibRuntimeError",
    "ResearchBundleIdentity",
    "UnsupportedFeatureError",
    "UnsupportedProcessorError",
    "VersionResolveError",
    "VersionResolver",
    "builtin_cs_zscore_processor",
    "builtin_identity_processor",
    "compute_bundle_hash",
    "default_runtime",
]
