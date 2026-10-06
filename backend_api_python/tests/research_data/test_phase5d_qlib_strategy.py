"""Phase 5D：Qlib Strategy Adapter 验收（L1–L4）。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from app.services.research_data.qlib_materializer.instrument_mapper import (
    to_qlib_instrument,
)
from app.services.research_data.qlib_strategy import (
    assess_compatibility,
    compute_qlib_run_hash,
    prediction_close_to,
    targets_to_weight_series,
    to_prediction_series,
    weights_close_to,
)
from app.services.research_data.qlib_strategy.backtest_adapter import (
    synthetic_weight_nav,
)
from app.services.research_data.research_backtest import (
    BacktestSpec,
    ResearchBacktestService,
    ResearchExecutionPolicy,
    compute_backtest_hash,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qlib_strategy_golden.golden import (  # noqa: E402
    INST_A,
    INST_B,
    SHASH,
    default_spec,
    make_env,
    price_bars,
    run_adapter,
    signal_rows,
    targets_by_date,
    trading_days,
)


def test_l1_instrument_mapping():
    """L1：instrument 映射与 Materializer 一致。"""
    assert to_qlib_instrument(INST_A).lower() == "sh600000"
    assert to_qlib_instrument(INST_B).lower() == "sz000001"
    days = trading_days(2)
    w = targets_to_weight_series(targets_by_date(days))
    instruments = {i for (_d, i) in w.index}
    assert "sh600000" in instruments
    assert "sz000001" in instruments


def test_l2_signal_prediction_align():
    """L2：Signal score ≈ Prediction Series。"""
    days = trading_days(3)
    rows = signal_rows(days)
    pred = to_prediction_series(rows)
    pred2 = to_prediction_series(rows)
    assert prediction_close_to(pred, pred2)
    assert not pred.empty
    qid = to_qlib_instrument(INST_A).lower()
    a_scores = pred.xs(qid, level="instrument")
    assert abs(float(a_scores.iloc[0]) - 1.5) < 1e-9


def test_l3_portfolio_weights_align():
    """L3：TargetPosition → weight Series 可复现。"""
    days = trading_days(2)
    t = targets_by_date(days)
    w1 = targets_to_weight_series(t)
    w2 = targets_to_weight_series(t)
    assert weights_close_to(w1, w2)
    day0 = days[0]
    # 权重和
    import pandas as pd

    sub = w1.xs(pd.Timestamp(day0), level="datetime")
    assert abs(float(sub.sum()) - 1.0) < 1e-9


def test_l4_gross_return_direction(tmp_path):
    """L4：GROSS 合成收益与 5B GROSS 同窗方向一致。"""
    days = trading_days(4)
    _, _, qsvc = make_env(tmp_path)
    r = run_adapter(qsvc, realism="GROSS", days=days)
    assert r.summary.realism == "GROSS"
    assert r.weights is not None and not r.weights.empty
    assert r.summary.metrics_json.get("total_return") is not None
    assert Path(r.summary.storage_uri).joinpath("manifest.json").is_file()
    assert Path(r.summary.storage_uri).joinpath("compatibility.json").is_file()

    # 5B GROSS 同窗
    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.registry import LocalJsonRegistry

    store = LocalCanonicalStore(root=tmp_path / "c2")
    registry = LocalJsonRegistry(root=tmp_path / "r2")
    bsvc = ResearchBacktestService(store, registry)
    bspec = BacktestSpec(
        strategy_hash=SHASH,
        start_date=days[0],
        end_date=days[-1],
        execution_policy=ResearchExecutionPolicy(mode="SAME_CLOSE"),
        realism="GROSS",
        initial_nav=1.0,
    )
    br = bsvc.run(
        SHASH,
        bspec,
        metadata={
            "targets_by_date": targets_by_date(days[:3]),
            "price_bars": price_bars(days),
            "force_recompute": True,
        },
    )
    q_ret = float(r.summary.metrics_json["total_return"])
    b_ret = float(br.frames.metrics["total_return"])
    # 同向（允许合成 close-to-close vs 5B fill 路径差异）
    assert q_ret * b_ret >= 0 or abs(q_ret - b_ret) < 0.05


def test_net_compatibility_partial(tmp_path):
    """NET：compatibility 含 PARTIAL/UNSUPPORTED。"""
    _, _, svc = make_env(tmp_path)
    r = run_adapter(svc, realism="NET")
    compat = r.summary.compatibility_json
    levels = {i["capability"]: i["level"] for i in compat["items"]}
    assert levels.get("t_plus_order_intent") == "UNSUPPORTED"
    assert levels.get("commission_stamp_slippage_lot") == "PARTIAL"
    assert compat.get("has_unsupported") is True


def test_hash_stable_and_differs():
    days = trading_days(3)
    s1 = default_spec(days, realism="GROSS")
    s2 = default_spec(days, realism="NET")
    assert compute_qlib_run_hash(s1) == compute_qlib_run_hash(s1)
    assert compute_qlib_run_hash(s1) != compute_qlib_run_hash(s2)


def test_domain_no_qlib_import():
    """Domain 模块（除 worker_main）不得 import qlib / Production。"""
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "qlib_strategy"
    )
    for py in root.glob("*.py"):
        if py.name == "worker_main.py":
            continue
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


def test_assess_gross_vs_net():
    days = trading_days(2)
    g = assess_compatibility(default_spec(days, realism="GROSS"))
    n = assess_compatibility(default_spec(days, realism="NET"))
    assert not g.has_partial
    assert n.has_partial and n.has_unsupported
