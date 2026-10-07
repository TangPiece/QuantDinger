"""Phase 7B：Shadow Trading Domain。"""

from .gateway import EnvironmentViolation, OrderExecutionGateway, is_real_broker
from .protocol import ENGINE_VERSION, ShadowCompareReport, ShadowOrder
from .runner import ShadowTradingService

__all__ = [
    "ENGINE_VERSION",
    "EnvironmentViolation",
    "OrderExecutionGateway",
    "ShadowCompareReport",
    "ShadowOrder",
    "ShadowTradingService",
    "is_real_broker",
]
