"""Repository：Gate/Cursor/Finding 持久化门面（委托 Writer）。"""

from __future__ import annotations

from .writers import ReconciliationWriter

# plan 命名：repository 与 writers 同职责
ReconciliationRepository = ReconciliationWriter

__all__ = ["ReconciliationRepository", "ReconciliationWriter"]
