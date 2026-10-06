"""PortfolioReconciliation Contract（无 Broker 拉仓；6F 实现）。"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

from .protocol import Account, Position
from .state_machine import assert_transition


class ExternalPosition(_ContractModel):
    instrument_key: str
    quantity: float = 0.0
    avg_cost: float = 0.0
    market_value: float = 0.0


class ExternalCash(_ContractModel):
    available_cash: float = 0.0
    frozen_cash: float = 0.0
    currency: str = "CNY"


class ReconciliationMismatch(_ContractModel):
    kind: Literal["quantity", "cash", "cost"] 
    instrument_key: str = ""
    internal: float = 0.0
    external: float = 0.0
    diff: float = 0.0
    message: str = ""


class ReconciliationReport(_ContractModel):
    """内部 vs 外部对账报告。"""

    account_id: str
    status: Literal["MATCHED", "MISMATCH", "RECONCILIATION_REQUIRED"] = "MATCHED"
    mismatches: list[ReconciliationMismatch] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def compare(
    account: Account,
    positions: Mapping[str, Position] | Sequence[Position],
    *,
    external_positions: Sequence[ExternalPosition | Mapping[str, Any]] | None = None,
    external_cash: ExternalCash | Mapping[str, Any] | None = None,
    qty_tol: float = 1e-6,
    cash_tol: float = 1e-4,
    cost_tol: float = 1e-4,
) -> ReconciliationReport:
    """比较内部持仓/现金与外部视图；无外部数据时 MATCHED。"""
    if isinstance(positions, dict):
        pos_map = positions
    else:
        pos_map = {p.instrument_key: p for p in positions}

    mismatches: list[ReconciliationMismatch] = []
    if external_cash is not None:
        ext = (
            external_cash
            if isinstance(external_cash, ExternalCash)
            else ExternalCash.model_validate(dict(external_cash))
        )
        d_av = float(account.cash.available_cash) - float(ext.available_cash)
        if abs(d_av) > cash_tol:
            mismatches.append(
                ReconciliationMismatch(
                    kind="cash",
                    internal=float(account.cash.available_cash),
                    external=float(ext.available_cash),
                    diff=d_av,
                    message="available_cash mismatch",
                )
            )

    for raw in external_positions or []:
        ep = (
            raw
            if isinstance(raw, ExternalPosition)
            else ExternalPosition.model_validate(dict(raw))
        )
        ip = pos_map.get(ep.instrument_key)
        iq = float(ip.quantity) if ip else 0.0
        dq = iq - float(ep.quantity)
        if abs(dq) > qty_tol:
            mismatches.append(
                ReconciliationMismatch(
                    kind="quantity",
                    instrument_key=ep.instrument_key,
                    internal=iq,
                    external=float(ep.quantity),
                    diff=dq,
                    message="quantity mismatch",
                )
            )
        if ip is not None and abs(float(ip.avg_cost) - float(ep.avg_cost)) > cost_tol:
            mismatches.append(
                ReconciliationMismatch(
                    kind="cost",
                    instrument_key=ep.instrument_key,
                    internal=float(ip.avg_cost),
                    external=float(ep.avg_cost),
                    diff=float(ip.avg_cost) - float(ep.avg_cost),
                    message="cost mismatch",
                )
            )

    if not mismatches:
        status: Literal["MATCHED", "MISMATCH", "RECONCILIATION_REQUIRED"] = "MATCHED"
    else:
        status = "RECONCILIATION_REQUIRED"
    return ReconciliationReport(
        account_id=account.account_id,
        status=status,
        mismatches=mismatches,
    )


def mark_reconciliation_required(account: Account) -> Account:
    """将账户状态置为 RECONCILIATION_REQUIRED。"""
    if account.status != "RECONCILIATION_REQUIRED":
        assert_transition(account.status, "RECONCILIATION_REQUIRED")
    return account.model_copy(update={"status": "RECONCILIATION_REQUIRED"})


class PortfolioReconciliation:
    """对账端口（6F 可接 Broker external）。"""

    def compare(
        self,
        account: Account,
        positions: Mapping[str, Position] | Sequence[Position],
        *,
        external_positions=None,
        external_cash=None,
    ) -> ReconciliationReport:
        return compare(
            account,
            positions,
            external_positions=external_positions,
            external_cash=external_cash,
        )
