"""Phase 7E：Capital Manager 写入的策略资金预算（策略不可自定账户资金）。"""

from __future__ import annotations

from .protocol import CapitalAllocation


class CapitalReject(RuntimeError):
    """资金分配或用量校验失败。"""


def validate_allocation(rec: CapitalAllocation) -> None:
    if rec.allocated_notional < 0 or rec.reserve_notional < 0:
        raise CapitalReject("allocated_notional/reserve must be non-negative")
    if rec.used_notional < 0:
        raise CapitalReject("used_notional must be non-negative")
    if rec.used_notional > rec.allocated_notional + 1e-9:
        raise CapitalReject("used_notional exceeds allocated_notional")


def remaining_notional(rec: CapitalAllocation) -> float:
    validate_allocation(rec)
    return max(0.0, rec.allocated_notional - rec.used_notional)


def check_order_notional(rec: CapitalAllocation, *, notional: float) -> tuple[bool, str]:
    """单笔 notional 是否超出剩余 allocated。"""
    if notional <= 0:
        return False, "notional_must_be_positive"
    rem = remaining_notional(rec)
    if notional > rem:
        return False, "capital_remaining_exceeded"
    return True, ""


def record_usage(rec: CapitalAllocation, *, notional: float) -> CapitalAllocation:
    ok, reason = check_order_notional(rec, notional=notional)
    if not ok:
        raise CapitalReject(reason)
    return rec.model_copy(update={"used_notional": rec.used_notional + notional})
