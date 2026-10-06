"""Repository 别名。"""

from __future__ import annotations

from .writers import SafetyWriter

SafetyRepository = SafetyWriter

__all__ = ["SafetyRepository", "SafetyWriter"]
