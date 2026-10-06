"""Phase 6G Trading Safety / Kill Switch（OMS 前 Fail-Closed 闸门）。"""

from __future__ import annotations

from .gate import SafetyGate
from .protocol import (
    ENGINE_VERSION,
    DEFAULT_HARD_LIMITS,
    EmergencyStopIntent,
    HardLimits,
    KillSwitch,
    SafetyContext,
    SafetyEvent,
    SafetyRule,
    SafetyState,
    TradingGateDecision,
)
from .runner import SafetyError, SafetyService
from .state_machine import SafetyStateError

__all__ = [
    "DEFAULT_HARD_LIMITS",
    "ENGINE_VERSION",
    "EmergencyStopIntent",
    "HardLimits",
    "KillSwitch",
    "SafetyContext",
    "SafetyError",
    "SafetyEvent",
    "SafetyGate",
    "SafetyRule",
    "SafetyService",
    "SafetyState",
    "SafetyStateError",
    "TradingGateDecision",
]
