"""Phase 6I：固定 E2E 场景矩阵（注入 TargetPosition + SimulatedBroker）。"""

from __future__ import annotations

from app.services.e2e_service.protocol import ScenarioSpec

INST = "USStock:AAPL"
FIXTURE = "e2e_fixture_v1"

# 场景 id 有序列表，供 suite 验收
ALL_SCENARIO_IDS = [f"E2E-{i:03d}" for i in range(1, 11)]


def _base(**overrides) -> ScenarioSpec:
    spec = ScenarioSpec(
        scenario_id="E2E-000",
        title="",
        fixture_id=FIXTURE,
        instrument_key=INST,
        target_quantity=100.0,
        side="BUY",
        execution_algorithm="MARKET",
        metadata={"dataset_hash": "e2e_dh_v1", "strategy_version": "e2e_sv_v1"},
    )
    if overrides:
        return spec.model_copy(update=overrides)
    return spec


_SCENARIOS: dict[str, ScenarioSpec] = {
    "E2E-001": _base(
        scenario_id="E2E-001",
        title="BUY partial fill complete",
        broker_inject={"partial_fills": [40.0, 60.0]},
        expect={"order_status": "FILLED", "recon_clean": True},
    ),
    "E2E-002": _base(
        scenario_id="E2E-002",
        title="BUY reject",
        broker_inject={"reject": True},
        expect={"order_status": "REJECTED"},
    ),
    "E2E-003": _base(
        scenario_id="E2E-003",
        title="BUY limit cancel",
        execution_algorithm="LIMIT",
        limit_price=5.0,
        post_actions=["cancel"],
        expect={"order_status": "CANCELLED"},
    ),
    "E2E-004": _base(
        scenario_id="E2E-004",
        title="partial then cancel",
        broker_inject={"partial_fills": [40.0]},
        post_actions=["cancel"],
        expect={"partial_before_cancel": True},
    ),
    "E2E-005": _base(
        scenario_id="E2E-005",
        title="broker disconnect",
        pre_actions=["disconnect"],
        expect={"health_degraded": True, "blocked": True},
    ),
    "E2E-006": _base(
        scenario_id="E2E-006",
        title="duplicate execution",
        target_quantity=10.0,
        broker_inject={"duplicate_execution": True},
        expect={"dedup": True},
    ),
    "E2E-007": _base(
        scenario_id="E2E-007",
        title="unknown recover",
        target_quantity=10.0,
        broker_inject={"timeout_unknown": True},
        post_actions=["recover_unknown"],
        expect={"recovered": True},
    ),
    "E2E-008": _base(
        scenario_id="E2E-008",
        title="position mismatch",
        broker_inject={"partial_fills": [100.0]},
        post_actions=["recon_mismatch"],
        expect={"recon_critical": True, "safety_block": True},
    ),
    "E2E-009": _base(
        scenario_id="E2E-009",
        title="risk reject",
        target_quantity=100.0,
        risk_policy_overrides={
            "max_single_position_weight": 0.001,
            "clip_on_limit": False,
        },
        expect={"risk_reject": True, "no_orders": True},
    ),
    "E2E-010": _base(
        scenario_id="E2E-010",
        title="kill switch",
        pre_actions=["kill_switch"],
        expect={"blocked": True, "kill_audit": True},
    ),
}


def get_scenario(scenario_id: str) -> ScenarioSpec:
    """按 id 取场景；不存在则 KeyError。"""
    key = str(scenario_id or "").strip().upper()
    if key not in _SCENARIOS:
        raise KeyError(scenario_id)
    return _SCENARIOS[key].model_copy(deep=True)


def list_scenarios() -> list[ScenarioSpec]:
    return [get_scenario(sid) for sid in ALL_SCENARIO_IDS]
