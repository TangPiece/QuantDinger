"""Position 对账：包装 6B compare → Finding。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.services.portfolio_service.protocol import Account, Position
from app.services.portfolio_service.reconciliation import (
    ExternalCash,
    ExternalPosition,
    compare as portfolio_compare,
)

from .findings import make_finding
from .protocol import BrokerSnapshot, ReconciliationFinding


def _severity_for_qty_diff(abs_diff: float, *, critical_threshold: float = 1.0) -> str:
    """|Δqty|≥阈值 → CRITICAL，否则 ERROR。"""
    if abs_diff >= critical_threshold:
        return "CRITICAL"
    return "ERROR"


def compare_positions(
    *,
    run_id: str,
    account: Account,
    positions: Mapping[str, Position] | Sequence[Position],
    snapshot: BrokerSnapshot,
    qty_tol: float = 1e-6,
    critical_qty_threshold: float = 1.0,
) -> list[ReconciliationFinding]:
    """复用 6B compare；quantity mismatch → POSITION_MISMATCH。"""
    ext_pos = [
        ExternalPosition(
            instrument_key=p.instrument_key,
            quantity=float(p.quantity),
            avg_cost=float(p.avg_cost),
            market_value=float(p.market_value),
        )
        for p in (snapshot.positions or [])
    ]
    # 内部有、外部无：补 0 量外部行以便 compare 检出
    if isinstance(positions, dict):
        pos_map = positions
    else:
        pos_map = {p.instrument_key: p for p in positions}
    known = {e.instrument_key for e in ext_pos}
    for ik, ip in pos_map.items():
        if ik not in known and abs(float(ip.quantity)) > qty_tol:
            ext_pos.append(
                ExternalPosition(instrument_key=ik, quantity=0.0, avg_cost=0.0)
            )

    report = portfolio_compare(
        account,
        pos_map,
        external_positions=ext_pos,
        external_cash=None,
        qty_tol=qty_tol,
    )
    findings: list[ReconciliationFinding] = []
    for m in report.mismatches:
        if m.kind != "quantity":
            continue
        sev = _severity_for_qty_diff(abs(float(m.diff)), critical_threshold=critical_qty_threshold)
        findings.append(
            make_finding(
                run_id=run_id,
                finding_type="POSITION_MISMATCH",
                severity=sev,  # type: ignore[arg-type]
                entity_type="POSITION",
                entity_id=m.instrument_key or "position",
                expected={"quantity": float(m.internal)},
                actual={"quantity": float(m.external)},
                difference={"diff": float(m.diff), "kind": m.kind},
            )
        )
    return findings
