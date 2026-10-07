"""Phase 6J：Production Readiness 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.production_readiness.modes import ReadinessModeError, assert_mode
from app.services.production_readiness.scenarios import ALL_SCENARIO_IDS

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readiness_golden.golden import DATASET_HASH, STRATEGY_VERSION, make_env  # noqa: E402


def _domain_isolation() -> bool:
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "production_readiness"
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
            if py.name == "modes.py":
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.strip().upper() == "LIVE":
                    return False
    return True


def test_ast_isolation():
    assert _domain_isolation()


def test_modes_forbid_live():
    with pytest.raises(ReadinessModeError):
        assert_mode("LIVE")


@pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
def test_scenario_ok(tmp_path, scenario_id):
    *_, rdy = make_env(tmp_path / scenario_id)
    result = rdy.run_scenario(scenario_id, salt=scenario_id)
    assert result.status == "OK", result.messages


def test_checklist_production_ready(tmp_path):
    *_, rdy = make_env(tmp_path / "checklist")
    checklist = rdy.run_checklist(salt="pytest")
    assert checklist.production_ready is True, [
        (c.check_id, c.status, c.messages) for c in checklist.checks if c.status != "OK"
    ]


def test_recover_on_start_no_resubmit(tmp_path):
    _, _, _, _, oms, *_ = make_env(tmp_path / "rec")
    report = oms.recover_on_start()
    assert report.resubmit_attempted is False
