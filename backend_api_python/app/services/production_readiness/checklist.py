"""Phase 6J：PRODUCTION_READY checklist 聚合。"""

from __future__ import annotations

from typing import Mapping

from .hash import derive_readiness_run_id
from .protocol import ChecklistResult, ReadinessCheck, ScenarioResult
from .scenarios import ALL_SCENARIO_IDS

# P0 检查项与 RDY 场景映射
CHECK_SCENARIO_MAP: dict[str, str] = {
    "crash_recovery": "RDY-001",
    "idempotency": "RDY-002",
    "execution_dedup": "RDY-003",
    "unknown_recover": "RDY-004",
    "out_of_order_execution": "RDY-005",
    "broker_reconnect": "RDY-006",
    "registry_persistence": "RDY-007",
    "kill_switch_isolation": "RDY-008",
    "operator_override": "RDY-009",
    "replay_pit": "RDY-010",
}

CHECK_TITLES: dict[str, str] = {
    "crash_recovery": "Crash Recovery / recover_on_start",
    "idempotency": "Order Idempotency",
    "execution_dedup": "Execution Deduplication",
    "unknown_recover": "UNKNOWN Order Recovery",
    "out_of_order_execution": "Out-of-Order Execution",
    "broker_reconnect": "Broker Disconnect Recovery",
    "registry_persistence": "Registry Restart Persistence",
    "kill_switch_isolation": "Kill Switch Isolation",
    "operator_override": "Operator Ack → Resume",
    "replay_pit": "Replay + PIT Leakage Stub",
}


def aggregate_checklist(
    scenario_results: Mapping[str, ScenarioResult],
    *,
    salt: str = "",
    recover_meta: dict | None = None,
) -> ChecklistResult:
    """全部 P0 检查通过则 production_ready=True。"""
    run_id = derive_readiness_run_id(salt=salt)
    checks: list[ReadinessCheck] = []
    all_ok = True
    for check_id, scenario_id in CHECK_SCENARIO_MAP.items():
        sr = scenario_results.get(scenario_id)
        if sr is None:
            all_ok = False
            checks.append(
                ReadinessCheck(
                    check_id=check_id,
                    title=CHECK_TITLES.get(check_id, check_id),
                    status="FAILED",
                    scenario_id=scenario_id,
                    messages=["scenario not run"],
                )
            )
            continue
        ok = sr.status == "OK"
        if not ok:
            all_ok = False
        checks.append(
            ReadinessCheck(
                check_id=check_id,
                title=CHECK_TITLES.get(check_id, check_id),
                status="OK" if ok else "FAILED",
                scenario_id=scenario_id,
                messages=list(sr.messages),
                metadata=dict(sr.metadata or {}),
            )
        )
    missing = [sid for sid in ALL_SCENARIO_IDS if sid not in scenario_results]
    if missing:
        all_ok = False
    return ChecklistResult(
        run_id=run_id,
        production_ready=all_ok and not missing,
        checks=checks,
        metadata={"missing_scenarios": missing, **(recover_meta or {})},
    )
