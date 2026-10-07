"""Phase 8D：Strategy Promotion Pipeline。"""

from .protocol import ENGINE_VERSION
from .runner import PromotionError, StrategyPromotionService

__all__ = ["ENGINE_VERSION", "PromotionError", "StrategyPromotionService"]
