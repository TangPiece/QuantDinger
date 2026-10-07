"""Phase 8C：Strategy Validation Gate（只读 Candidate → ValidationRun）。"""

from .protocol import ENGINE_VERSION
from .runner import ValidationGateError, ValidationGateService

__all__ = ["ENGINE_VERSION", "ValidationGateError", "ValidationGateService"]
