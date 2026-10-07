"""Phase 9F-1 — Model Platform (Contract & Registry)."""

from .protocol import ENGINE_VERSION
from .runner import ModelPlatformError, ModelPlatformService

__all__ = [
    "ENGINE_VERSION",
    "ModelPlatformError",
    "ModelPlatformService",
]
