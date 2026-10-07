"""Phase 6J：RDY-001…010 固定场景矩阵。"""

from __future__ import annotations

from app.services.production_readiness.protocol import ScenarioSpec

INST = "USStock:AAPL"
FIXTURE = "rdy_fixture_v1"

ALL_SCENARIO_IDS = [f"RDY-{i:03d}" for i in range(1, 11)]


def _base(**overrides) -> ScenarioSpec:
    spec = ScenarioSpec(
        scenario_id="RDY-000",
        title="",
        fixture_id=FIXTURE,
        instrument_key=INST,
        target_quantity=100.0,
        side="BUY",
        execution_algorithm="MARKET",
        metadata={"dataset_hash": "rdy_dh_v1", "strategy_version": "rdy_sv_v1"},
    )
    if overrides:
        return spec.model_copy(update=overrides)
    return spec


_SCENARIOS: dict[str, ScenarioSpec] = {
    "RDY-001": _base(
        scenario_id="RDY-001",
        title="Crash after SUBMITTED — recover_on_start no re-submit",
        metadata={"async_submit": True},
        post_actions=["broker_submit_only", "recover_on_start"],
        expect={"order_status": "FILLED", "no_resubmit": True},
    ),
    "RDY-002": _base(
        scenario_id="RDY-002",
        title="Idempotent triple submit",
        target_quantity=10.0,
        post_actions=["triple_submit"],
        expect={"single_broker_order": True},
    ),
    "RDY-003": _base(
        scenario_id="RDY-003",
        title="Dedup after reconnect",
        target_quantity=10.0,
        broker_inject={"duplicate_execution": True},
        post_actions=["reconnect_pump"],
        expect={"dedup": True},
    ),
    "RDY-004": _base(
        scenario_id="RDY-004",
        title="UNKNOWN recover",
        target_quantity=10.0,
        broker_inject={"timeout_unknown": True},
        post_actions=["recover_unknown"],
        expect={"recovered": True},
    ),
    "RDY-005": _base(
        scenario_id="RDY-005",
        title="Out-of-order execution final qty",
        target_quantity=100.0,
        broker_inject={"partial_fills": [60.0, 40.0]},
        post_actions=["apply_out_of_order"],
        expect={"filled_qty": 100.0},
    ),
    "RDY-006": _base(
        scenario_id="RDY-006",
        title="Broker disconnect + reconnect merge",
        target_quantity=10.0,
        broker_inject={"ws_disconnect_after_n": 1},
        post_actions=["reconnect_pump"],
        expect={"order_status": "FILLED", "dedup": True},
    ),
    "RDY-007": _base(
        scenario_id="RDY-007",
        title="Registry restart persistence",
        target_quantity=5.0,
        post_actions=["registry_restart_check"],
        expect={"registry_persist": True},
    ),
    "RDY-008": _base(
        scenario_id="RDY-008",
        title="Kill Switch strategy/account/global isolation",
        pre_actions=["kill_strategy"],
        expect={"strategy_blocked": True, "other_allowed": True},
    ),
    "RDY-009": _base(
        scenario_id="RDY-009",
        title="Operator ack → resume + audit actor",
        pre_actions=["kill_account"],
        post_actions=["ack_resume"],
        expect={"audit_resume": True},
    ),
    "RDY-010": _base(
        scenario_id="RDY-010",
        title="Replay + PIT leakage stub",
        post_actions=["replay_twice", "pit_leakage_check"],
        expect={"replay_ok": True, "pit_reject": True},
    ),
}


def get_scenario(scenario_id: str) -> ScenarioSpec:
    key = str(scenario_id or "").strip().upper()
    if key not in _SCENARIOS:
        raise KeyError(scenario_id)
    return _SCENARIOS[key].model_copy(deep=True)


def list_scenarios() -> list[ScenarioSpec]:
    return [get_scenario(sid) for sid in ALL_SCENARIO_IDS]
