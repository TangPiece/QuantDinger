"""P&L 轻量对账：容差 + fees 归因 stub。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.portfolio_service.protocol import Account

from .findings import make_finding
from .protocol import BrokerSnapshot, ReconciliationFinding


def compare_pnl(
    *,
    run_id: str,
    account: Account,
    snapshot: BrokerSnapshot,
    pnl_tol: float = 1.0,
    metadata: Mapping[str, Any] | None = None,
) -> list[ReconciliationFinding]:
    """内部 realized/unrealized stub vs broker equity−cash；默认 INFO/WARNING。"""
    meta = dict(metadata or {})
    # 内部 P&L：优先 metadata，否则 market_value 近似
    internal_pnl = float(
        meta.get("internal_pnl")
        if meta.get("internal_pnl") is not None
        else getattr(account, "market_value", 0.0) or 0.0
    )
    broker_equity = float(snapshot.account.equity or 0.0)
    broker_cash = float(snapshot.account.cash or 0.0)
    # stub：equity − cash ≈ 持仓市值贡献
    broker_pnl = float(
        meta.get("broker_pnl")
        if meta.get("broker_pnl") is not None
        else (broker_equity - broker_cash)
    )
    fees = float(meta.get("fees") or 0.0)
    # 费用归因：差值中扣除 fees 后再判
    raw_diff = internal_pnl - broker_pnl
    attributed = raw_diff - fees
    if abs(attributed) <= pnl_tol:
        if abs(raw_diff) > 1e-9:
            return [
                make_finding(
                    run_id=run_id,
                    finding_type="PNL_MISMATCH",
                    severity="INFO",
                    entity_type="PNL",
                    entity_id=account.account_id,
                    expected={"pnl": internal_pnl},
                    actual={"pnl": broker_pnl},
                    difference={
                        "raw_diff": raw_diff,
                        "fees": fees,
                        "attributed_diff": attributed,
                        "within_tolerance": True,
                    },
                )
            ]
        return []
    sev = "WARNING" if abs(attributed) < pnl_tol * 10 else "ERROR"
    return [
        make_finding(
            run_id=run_id,
            finding_type="PNL_MISMATCH",
            severity=sev,  # type: ignore[arg-type]
            entity_type="PNL",
            entity_id=account.account_id,
            expected={"pnl": internal_pnl},
            actual={"pnl": broker_pnl},
            difference={
                "raw_diff": raw_diff,
                "fees": fees,
                "attributed_diff": attributed,
            },
        )
    ]
