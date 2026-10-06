"""Phase 5C：Cost & Execution Model（研究侧执行仿真层）。"""

from .attribution import build_attribution
from .market_rules import fingerprint_policies, resolve_market_bundle
from .order_builder import build_order_intents, portfolio_from_shares
from .protocol import (
    EXECUTION_PROFILE_VERSION,
    AttributionBreakdown,
    AttributionReport,
    DailyCostRow,
    ExecutionPricePolicy,
    ExecutionProfile,
    FillRow,
)
from .simulator import ResearchExecutionSimulator

__all__ = [
    "EXECUTION_PROFILE_VERSION",
    "AttributionBreakdown",
    "AttributionReport",
    "DailyCostRow",
    "ExecutionPricePolicy",
    "ExecutionProfile",
    "FillRow",
    "ResearchExecutionSimulator",
    "build_attribution",
    "build_order_intents",
    "fingerprint_policies",
    "portfolio_from_shares",
    "resolve_market_bundle",
]
