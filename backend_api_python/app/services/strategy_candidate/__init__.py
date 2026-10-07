"""Phase 8B：Strategy Candidate（Research lineage → 可治理候选）。"""

from .protocol import ENGINE_VERSION, PromotionRecord, StrategyCandidateRecord
from .runner import CandidateError, LineageImmutableError, StrategyCandidateService

__all__ = [
    "ENGINE_VERSION",
    "CandidateError",
    "LineageImmutableError",
    "PromotionRecord",
    "StrategyCandidateRecord",
    "StrategyCandidateService",
]
