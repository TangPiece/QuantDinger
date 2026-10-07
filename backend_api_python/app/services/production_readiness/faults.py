"""Phase 6J：故障注入 catalog + 可执行子集。"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .protocol import FaultCase, FaultResult

_FAULT_CATALOG: list[FaultCase] = [
    FaultCase(
        fault_id="FLT-BROKER-DISCONNECT",
        title="Broker WebSocket disconnect",
        category="broker",
        expected_behavior="Health DEGRADED; no duplicate orders on reconnect",
        recovery_procedure="reconnect_ws + REST snapshot + dedup pump",
        runnable=True,
    ),
    FaultCase(
        fault_id="FLT-DUP-EXEC",
        title="Duplicate execution event",
        category="broker",
        expected_behavior="Position increases once",
        recovery_procedure="ExecutionDeduper + reconciliation",
        runnable=True,
    ),
    FaultCase(
        fault_id="FLT-UNKNOWN-ORDER",
        title="Submit timeout UNKNOWN",
        category="oms",
        expected_behavior="recover_unknown query only",
        recovery_procedure="recover_on_start / recover_unknown_order",
        runnable=True,
    ),
    FaultCase(
        fault_id="FLT-R2-TIMEOUT",
        title="R2 temporarily unavailable",
        category="storage",
        expected_behavior="OMS state in D1/Registry remains readable",
        recovery_procedure="Retry artifact write; trading reads registry",
        runnable=False,
    ),
    FaultCase(
        fault_id="FLT-RECON-MISMATCH",
        title="Reconciliation CRITICAL",
        category="recon",
        expected_behavior="Safety BLOCK new orders",
        recovery_procedure="Operator ack + fix drift + resume",
        runnable=False,
    ),
]


def list_fault_cases() -> list[FaultCase]:
    return [f.model_copy(deep=True) for f in _FAULT_CATALOG]


def get_fault_case(fault_id: str) -> FaultCase:
    key = str(fault_id or "").strip().upper()
    for f in _FAULT_CATALOG:
        if f.fault_id.upper() == key:
            return f.model_copy(deep=True)
    raise KeyError(fault_id)


def run_fault(
    fault_id: str,
    *,
    run_scenario: Callable[[str], Any],
) -> FaultResult:
    """冒烟可执行故障：映射到 RDY 场景。"""
    fid = str(fault_id or "").strip().upper()
    mapping = {
        "FLT-BROKER-DISCONNECT": "RDY-006",
        "FLT-DUP-EXEC": "RDY-003",
        "FLT-UNKNOWN-ORDER": "RDY-004",
    }
    scenario_id = mapping.get(fid)
    if not scenario_id:
        case = get_fault_case(fault_id)
        return FaultResult(
            fault_id=case.fault_id,
            status="SKIPPED",
            expected_behavior=case.expected_behavior,
            actual_behavior="not runnable in verify smoke",
            messages=["catalog entry only"],
        )
    sr = run_scenario(scenario_id)
    ok = getattr(sr, "status", "") == "OK"
    return FaultResult(
        fault_id=fid,
        status="OK" if ok else "FAILED",
        expected_behavior=get_fault_case(fault_id).expected_behavior,
        actual_behavior=f"scenario {scenario_id} status={getattr(sr, 'status', '')}",
        messages=list(getattr(sr, "messages", []) or []),
    )


def list_slos() -> list:
    from .protocol import TradingSLO

    return [
        TradingSLO(
            slo_id="slo-idempotency",
            name="Order Idempotency",
            target_ratio=1.0,
            metric_name="orders_idempotent_ratio",
            description="Duplicate submits must not create duplicate broker orders",
        ),
        TradingSLO(
            slo_id="slo-exec-dedup",
            name="Execution Deduplication",
            target_ratio=1.0,
            metric_name="execution_dedup_ratio",
        ),
        TradingSLO(
            slo_id="slo-crash-recover",
            name="E2E Crash Recovery",
            target_ratio=1.0,
            metric_name="recover_on_start_success_ratio",
        ),
        TradingSLO(
            slo_id="slo-recon-freshness",
            name="Reconciliation Freshness",
            target_ratio=0.99,
            window_sec=30.0,
            metric_name="recon_freshness_sec",
            description="Target <30s; adjust per deployment",
        ),
    ]
