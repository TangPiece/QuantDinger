"""Phase 3C：Trading Cost & Execution Rules（引擎无关；禁止 import qlib）。"""

from .calendar import (
    CalendarError,
    intended_execution_datetime,
    list_trading_days,
    resolve_execution_date,
)
from .cost import compute_cost_breakdown
from .eligibility import SuspensionFailError, build_eligibility, decide_execution
from .lot import LotAdjustResult, adjust_lot_quantity, round_price_to_tick
from .models import (
    REASON_EXECUTION_DELAY,
    REASON_HOLD,
    REASON_INSUFFICIENT_CASH,
    REASON_LIMIT_DOWN,
    REASON_LIMIT_UP,
    REASON_LOT_SIZE_FLOOR,
    REASON_LOT_SIZE_REJECT,
    REASON_NO_PRICE,
    REASON_OK,
    REASON_SHORT_NOT_ALLOWED,
    REASON_SUSPENDED,
    REASON_T_PLUS,
    CostBreakdown,
    EligibilityFlags,
    ExecutionDecision,
    MarketBar,
)
from .presets_market import (
    cn_a_share_execution_bundle,
    hk_equity_t0_close,
    us_equity_t0_close,
)
from .rebalance import target_quantity_from_weight, targets_to_order_intents
from .simulator import ExecutionSimulator, PipelineResult, StepResult, run_pipeline

__all__ = [
    "CalendarError",
    "CostBreakdown",
    "EligibilityFlags",
    "ExecutionDecision",
    "ExecutionSimulator",
    "LotAdjustResult",
    "MarketBar",
    "PipelineResult",
    "REASON_EXECUTION_DELAY",
    "REASON_HOLD",
    "REASON_INSUFFICIENT_CASH",
    "REASON_LIMIT_DOWN",
    "REASON_LIMIT_UP",
    "REASON_LOT_SIZE_FLOOR",
    "REASON_LOT_SIZE_REJECT",
    "REASON_NO_PRICE",
    "REASON_OK",
    "REASON_SHORT_NOT_ALLOWED",
    "REASON_SUSPENDED",
    "REASON_T_PLUS",
    "StepResult",
    "SuspensionFailError",
    "adjust_lot_quantity",
    "build_eligibility",
    "cn_a_share_execution_bundle",
    "compute_cost_breakdown",
    "decide_execution",
    "hk_equity_t0_close",
    "intended_execution_datetime",
    "list_trading_days",
    "resolve_execution_date",
    "round_price_to_tick",
    "run_pipeline",
    "target_quantity_from_weight",
    "targets_to_order_intents",
    "us_equity_t0_close",
]
