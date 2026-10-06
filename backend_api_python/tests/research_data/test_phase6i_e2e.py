"""Phase 6I：Paper / Shadow E2E 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.e2e_service.modes import E2EModeError, assert_mode
from app.services.e2e_service.protocol import ReplayRequest
from app.services.e2e_service.scenarios import ALL_SCENARIO_IDS

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_golden.golden import (  # noqa: E402
    DATASET_HASH,
    STRATEGY_VERSION,
    make_env,
)


def _domain_isolation() -> bool:
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "e2e_service"
    )
    forbidden = (
        "qlib",
        "strategy_v2",
        "live_trading",
        "pending_order",
        "DataSourceFactory",
    )
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    for frag in forbidden:
                        if frag in name:
                            return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for frag in forbidden:
                    if frag in mod:
                        return False
            # modes.py 需引用 LIVE 字面量以 Fail-Closed 拒绝
            if py.name == "modes.py":
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.strip().upper() == "LIVE":
                    return False
    return True


def test_ast_isolation():
    assert _domain_isolation()


def test_modes_forbid_live():
    with pytest.raises(E2EModeError):
        assert_mode("LIVE")


@pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
def test_scenario_ok(tmp_path, scenario_id):
    *_, e2e = make_env(tmp_path / scenario_id)
    e2e.start_session(
        dataset_hash=DATASET_HASH,
        strategy_version=STRATEGY_VERSION,
        salt=scenario_id,
    )
    result = e2e.run_scenario(scenario_id, salt=scenario_id)
    assert result.status == "OK", result.messages


def test_suite_paper(tmp_path):
    *_, e2e = make_env(tmp_path / "suite")
    results = e2e.run_suite(mode="PAPER", salt="suite")
    assert len(results) == len(ALL_SCENARIO_IDS)
    assert all(r.status == "OK" for r in results), [
        (r.scenario_id, r.messages) for r in results if r.status != "OK"
    ]


def test_shadow_stops_with_virtual_order(tmp_path):
    *_, e2e = make_env(tmp_path / "shadow")
    e2e.start_session(mode="SHADOW", salt="sh")
    r = e2e.run_scenario("E2E-001", mode="SHADOW", salt="sh")
    assert r.status == "OK"
    assert r.virtual_orders and not r.order_ids


def test_replay_deterministic(tmp_path):
    *_, e2e = make_env(tmp_path / "replay")
    rep = e2e.replay(
        ReplayRequest(
            dataset_hash=DATASET_HASH,
            strategy_version=STRATEGY_VERSION,
            fixture_id="e2e_fixture_v1",
            scenario_id="E2E-001",
        )
    )
    assert rep.ok and not rep.drift_detected
    assert rep.first_fingerprint == rep.second_fingerprint


def test_consistency_score(tmp_path):
    *_, e2e = make_env(tmp_path / "score")
    results = e2e.run_suite(mode="PAPER", salt="sc")
    run_id = results[0].run_id
    score = e2e.consistency_score(run_id)
    assert score.overall > 0.5


def test_shadow_compare(tmp_path):
    *_, e2e = make_env(tmp_path / "cmp")
    salt = "cmp_same"
    e2e.start_session(mode="PAPER", salt=salt)
    pr = e2e.run_scenario("E2E-001", mode="PAPER", salt=salt)
    e2e.start_session(mode="SHADOW", salt=salt)
    sr = e2e.run_scenario("E2E-001", mode="SHADOW", salt=salt)
    cmp = e2e.shadow_compare(
        pr.run_id, sr.run_id, scenario_id="E2E-001"
    )
    assert cmp.intent_match
