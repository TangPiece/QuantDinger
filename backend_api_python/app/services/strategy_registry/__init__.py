"""Phase 8A：Strategy Registry（身份 + 版本 + Policy 绑定 SSOT）。"""

from .protocol import (
    ENGINE_VERSION,
    PolicyBindings,
    StrategyRecord,
    StrategyVersionRecord,
)
from .runner import (
    RegistryError,
    StrategyRegistryService,
    VersionImmutableError,
)

__all__ = [
    "ENGINE_VERSION",
    "PolicyBindings",
    "RegistryError",
    "StrategyRecord",
    "StrategyRegistryService",
    "StrategyVersionRecord",
    "VersionImmutableError",
]
