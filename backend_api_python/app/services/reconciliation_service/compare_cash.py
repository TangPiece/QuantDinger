"""Cash 对账：内部 available_cash vs Snapshot.account.cash。"""

from __future__ import annotations

from app.services.portfolio_service.protocol import Account

from .findings import make_finding
from .protocol import BrokerSnapshot, ReconciliationFinding


def compare_cash(
    *,
    run_id: str,
    account: Account,
    snapshot: BrokerSnapshot,
    cash_tol: float = 1e-4,
    warning_threshold: float = 1.0,
) -> list[ReconciliationFinding]:
    """CASH_MISMATCH；默认 WARNING，大额差 ERROR。"""
    internal = float(account.cash.available_cash)
    external = float(snapshot.account.cash)
    diff = internal - external
    if abs(diff) <= cash_tol:
        return []
    sev = "ERROR" if abs(diff) >= warning_threshold else "WARNING"
    return [
        make_finding(
            run_id=run_id,
            finding_type="CASH_MISMATCH",
            severity=sev,  # type: ignore[arg-type]
            entity_type="CASH",
            entity_id=account.account_id,
            expected={"available_cash": internal},
            actual={"cash": external},
            difference={"diff": diff},
        )
    ]
