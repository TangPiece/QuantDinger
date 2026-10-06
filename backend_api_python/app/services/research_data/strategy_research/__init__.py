"""Phase 5A：Strategy Research Foundation。"""

from app.services.research_data.contracts import (
    ResearchStrategyRecord,
    StrategyResearchSummary,
)

from .hash import compute_strategy_hash
from .lookahead import LookAheadError, assert_no_lookahead
from .orchestrator import (
    StrategyResearchError,
    StrategyResearchService,
    StrategyResult,
)
from .protocol import (
    STRATEGY_VERSION,
    HoldingRule,
    RebalanceRule,
    SignalDefinition,
    StrategySpec,
)

__all__ = [
    "STRATEGY_VERSION",
    "HoldingRule",
    "LookAheadError",
    "RebalanceRule",
    "ResearchStrategyRecord",
    "SignalDefinition",
    "StrategyResearchError",
    "StrategyResearchService",
    "StrategyResearchSummary",
    "StrategyResult",
    "StrategySpec",
    "assert_no_lookahead",
    "compute_strategy_hash",
]
