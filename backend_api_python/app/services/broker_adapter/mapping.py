"""券商 raw status → OMS ExecutionReport.status。"""

from __future__ import annotations

# Simulated / 通用映射表
_SIMULATED_MAP: dict[str, str] = {
    "NEW": "ACK",
    "ACCEPTED": "ACK",
    "SUBMITTED": "ACK",
    "ACKNOWLEDGED": "ACK",
    "PARTIALLY_FILLED": "PARTIAL",
    "PARTIAL": "PARTIAL",
    "FILLED": "FILL",
    "FILL": "FILL",
    "CANCELED": "CANCEL",
    "CANCELLED": "CANCEL",
    "CANCEL": "CANCEL",
    "REJECTED": "REJECT",
    "REJECT": "REJECT",
    "EXPIRED": "CANCEL",
    "UNKNOWN": "UNKNOWN",
    "PENDING_NEW": "ACK",
}

# Alpaca Paper 常见状态
_ALPACA_MAP: dict[str, str] = {
    "new": "ACK",
    "accepted": "ACK",
    "pending_new": "ACK",
    "accepted_for_bidding": "ACK",
    "partially_filled": "PARTIAL",
    "filled": "FILL",
    "done_for_day": "FILL",
    "canceled": "CANCEL",
    "cancelled": "CANCEL",
    "expired": "CANCEL",
    "replaced": "ACK",
    "pending_cancel": "ACK",
    "pending_replace": "ACK",
    "rejected": "REJECT",
    "stopped": "CANCEL",
    "suspended": "UNKNOWN",
    "calculated": "ACK",
}


def map_broker_status(raw: str, *, broker: str = "simulated") -> str:
    """将券商状态映射为 OMS ExecutionReport.status。"""
    key = str(raw or "").strip()
    if broker == "alpaca":
        mapped = _ALPACA_MAP.get(key.lower())
        if mapped:
            return mapped
    upper = key.upper()
    return _SIMULATED_MAP.get(upper, "UNKNOWN")
