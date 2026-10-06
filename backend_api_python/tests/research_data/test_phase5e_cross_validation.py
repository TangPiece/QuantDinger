"""Phase 5E：Cross Validation 验收（L1–L7 + AST）。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from app.services.research_data.cross_validation import compute_cv_hash
from app.services.research_data.cross_validation.dataset_diff import diff_dataset
from app.services.research_data.cross_validation.pit_diff import diff_pit
from app.services.research_data.cross_validation.signal_diff import diff_signal
from app.services.research_data.cross_validation.portfolio_diff import diff_portfolio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cross_validation_golden.golden import (  # noqa: E402
    INST_A,
    default_spec,
    make_env,
    run_cv,
    signal_rows,
    targets_by_date,
    trading_days,
)
from app.services.research_data.cross_validation.loaders import (  # noqa: E402
    build_prediction_records,
    build_weight_records,
)


def test_l1_dataset_identity(tmp_path):
    """L1：同一 materialization / dataset_hash。"""
    _, _, svc = make_env(tmp_path)
    r = run_cv(svc, realism="GROSS")
    by = {L.layer: L for L in r.layers}
    assert by["dataset"].status == "PASS"


def test_l2_pit_and_leakage():
    """L2：PIT 约束 + 未来泄漏不得进入历史。"""
    days = trading_days(3)
    rows = signal_rows(days)
    # 合法 PIT
    for r in rows:
        r["knowledge_time"] = f"{r['trading_date']}T15:00:00+08:00"
        r["available_time"] = f"{r['trading_date']}T12:00:00+08:00"
        r["execution_time"] = f"{r['trading_date']}T09:30:00+08:00"
        # 次日执行：修正为 T+1
        from datetime import date, timedelta

        d = date.fromisoformat(r["trading_date"])
        r["execution_time"] = f"{(d + timedelta(days=1)).isoformat()}T09:30:00+08:00"
    assert diff_pit(rows).status == "PASS"

    future = [
        {
            "instrument_key": INST_A,
            "trading_date": days[0].isoformat(),
            "score": 1.5,
            "must_not_appear_in_history": True,
        }
    ]
    # 与历史完全相同 score → 泄漏 FAIL
    assert diff_pit(rows, future_leak_rows=future).status == "FAIL"


def test_l3_universe(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = run_cv(svc)
    by = {L.layer: L for L in r.layers}
    assert by["universe"].status == "PASS"
    assert by["universe"].details.get("qd_snapshot") == "snap_5e_golden"


def test_l4_signal_align():
    days = trading_days(3)
    rows = signal_rows(days)
    a = build_prediction_records(rows)
    b = build_prediction_records(rows)
    assert diff_signal(a, b).status == "PASS"


def test_l5_portfolio_align():
    days = trading_days(3)
    t = targets_by_date(days)
    a = build_weight_records(t)
    b = build_weight_records(t)
    assert diff_portfolio(a, b).status == "PASS"


def test_l6_l7_gross_e2e(tmp_path):
    """L6/L7 + Perf：GROSS baseline 端到端。"""
    _, registry, svc = make_env(tmp_path)
    r = run_cv(svc, realism="GROSS")
    by = {L.layer: L for L in r.layers}
    assert by["execution"].status == "PASS"
    assert by["nav"].status == "PASS"
    assert by["performance"].status == "PASS"
    assert r.report.status in ("PASSED", "PASSED_WITH_EXPECTED_DIFF")
    assert registry.get_research_cross_validation(r.cv_hash)
    art = Path(r.summary.storage_uri)
    assert (art / "report.json").is_file()
    assert (art / "attribution.json").is_file()
    assert (art / "layers" / "nav.json").is_file()


def test_net_expected_difference(tmp_path):
    """NET：允许 EXPECTED_DIFFERENCE，不要求收益全等。"""
    _, _, svc = make_env(tmp_path)
    r = run_cv(svc, realism="NET")
    by = {L.layer: L for L in r.layers}
    assert by["execution"].kind in ("SEMANTIC", "EXPECTED_DIFFERENCE")
    assert r.report.status in ("PASSED", "PASSED_WITH_EXPECTED_DIFF", "FAILED")
    # 若 NAV 因成本模型 FAIL，attribution 应含 cost note；核心是报告可解释
    assert r.report.attribution.notes or by["execution"].status == "PASS"


def test_hash_stable():
    days = trading_days(3)
    s1 = default_spec(days, realism="GROSS")
    s2 = default_spec(days, realism="NET")
    assert compute_cv_hash(s1) == compute_cv_hash(s1)
    assert compute_cv_hash(s1) != compute_cv_hash(s2)


def test_domain_no_qlib_or_production():
    """Domain 包不得 import qlib / Production。"""
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "cross_validation"
    )
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    assert name != "qlib" and not name.startswith("qlib.")
                    assert "backtest_production" not in name
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("qlib")
                assert "backtest_production" not in mod
                for alias in node.names or []:
                    assert alias.name != "ProductionBacktestEngine"


def test_dataset_diff_unit():
    a = {"materialization_id": "m1", "dataset_hash": "d1"}
    b = {"materialization_id": "m1", "dataset_hash": "d1"}
    assert diff_dataset(a, b).status == "PASS"
    assert diff_dataset(a, {"materialization_id": "m2", "dataset_hash": "d1"}).status == "FAIL"
