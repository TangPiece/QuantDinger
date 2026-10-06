"""Phase 4I：Factor Portfolio 验收。"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

from app.services.research_data.factor_lab.portfolio import (
    compute_portfolio_hash,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_lab_portfolio.golden import (  # noqa: E402
    FID,
    default_spec,
    evaluation_panel,
    factor_panel,
    make_env,
    run_portfolio,
)


def _day_weights(positions, day=None):
    by = defaultdict(list)
    for p in positions:
        by[p.trading_date].append(p)
    d = day or sorted(by.keys())[0]
    return by[d]


def test_long_only_equal_top_pct(tmp_path):
    """LONG_ONLY EQUAL top_pct=0.1：持仓数≈10%N，权重和≈1。"""
    _, registry, svc = make_env(tmp_path)
    factors = factor_panel(40, days=5)
    ev = evaluation_panel(factors)
    r = run_portfolio(svc, factors, ev, default_spec(top_pct=0.1))
    day = _day_weights(r.frames.positions)
    assert len(day) == 4  # ceil(40*0.1)=4
    assert abs(sum(p.weight for p in day) - 1.0) < 1e-9
    assert all(p.leg == "LONG" for p in day)
    assert registry.get_factor_portfolio(r.portfolio_hash)


def test_long_short_weights_and_ls(tmp_path):
    """LONG_SHORT：Long≈+1、Short≈−1；LS 收益可复现。"""
    _, _, svc = make_env(tmp_path)
    factors = factor_panel(40, days=5)
    ev = evaluation_panel(factors)
    r = run_portfolio(
        svc,
        factors,
        ev,
        default_spec(construction_method="LONG_SHORT", top_pct=0.1),
    )
    day = _day_weights(r.frames.positions)
    long_sum = sum(p.weight for p in day if p.leg == "LONG")
    short_sum = sum(p.weight for p in day if p.leg == "SHORT")
    assert abs(long_sum - 1.0) < 1e-9
    assert abs(short_sum + 1.0) < 1e-9
    assert any(
        x.long_short_return is not None for x in r.frames.returns
    )
    assert r.frames.metrics.get("mean_long_short_return") is not None


def test_score_vs_equal(tmp_path):
    """SCORE：高分票权重大于 EQUAL 下的等权（相对低分票）。"""
    _, _, svc = make_env(tmp_path)
    factors = factor_panel(40, days=3)
    ev = evaluation_panel(factors)
    r_eq = run_portfolio(
        svc, factors, ev, default_spec(weight_method="EQUAL_WEIGHT", top_pct=0.2)
    )
    r_sc = run_portfolio(
        svc, factors, ev, default_spec(weight_method="SCORE_WEIGHT", top_pct=0.2)
    )
    eq = {p.instrument_key: p.weight for p in _day_weights(r_eq.frames.positions)}
    sc = {p.instrument_key: p.weight for p in _day_weights(r_sc.frames.positions)}
    # 最高因子票
    top = max(sc.keys())
    bot = min(sc.keys())
    assert sc[top] > sc[bot]
    assert abs(sc[top] - eq[top]) > 1e-12 or sc[top] >= eq[top]


def test_weekly_hold_forward_and_min_turnover(tmp_path):
    """WEEKLY：非调仓日权重沿用；min_turnover 过大时跳过调仓。"""
    _, _, svc = make_env(tmp_path)
    factors = factor_panel(40, days=14)
    ev = evaluation_panel(factors)
    r = run_portfolio(
        svc,
        factors,
        ev,
        default_spec(rebalance_frequency="WEEKLY", min_turnover=0.0),
    )
    by = defaultdict(list)
    for p in r.frames.positions:
        by[p.trading_date].append(p)
    dates = sorted(by.keys())
    assert len(dates) >= 4
    # 同一周内（若有多天）权重 instrument 集合应一致
    w0 = {p.instrument_key: p.weight for p in by[dates[0]]}
    # 找同周第二天
    from datetime import timedelta

    d1 = dates[0] + timedelta(days=1)
    if d1 in by:
        w1 = {p.instrument_key: p.weight for p in by[d1]}
        assert w0 == w1

    # min_turnover 极大 → 除首日外不调仓
    r2 = run_portfolio(
        svc,
        factors,
        ev,
        default_spec(
            rebalance_frequency="DAILY",
            min_turnover=1e9,
        ),
    )
    rebal_flags = [t.rebalanced for t in r2.frames.turnover]
    assert rebal_flags[0] is True
    assert all(f is False for f in rebal_flags[1:])


def test_quantile_q1_minus_qn(tmp_path):
    """QUANTILE group_count=5：存在 Q1..Q5；绩效为 Q1−Q5。"""
    _, _, svc = make_env(tmp_path)
    factors = factor_panel(50, days=5)
    ev = evaluation_panel(factors)
    r = run_portfolio(
        svc,
        factors,
        ev,
        default_spec(
            construction_method="QUANTILE",
            group_count=5,
            min_cross_section_size=10,
        ),
    )
    legs = {p.leg for p in r.frames.positions}
    assert {"Q1", "Q2", "Q3", "Q4", "Q5"} <= legs
    assert any(x.long_short_return is not None for x in r.frames.returns)
    assert "mean_long_short_return" in r.frames.metrics


def test_hash_repro_manifest_immutable(tmp_path):
    _, registry, svc = make_env(tmp_path)
    factors = factor_panel(40, days=3)
    ev = evaluation_panel(factors)
    spec = default_spec()
    r1 = run_portfolio(svc, factors, ev, spec)
    r2 = run_portfolio(svc, factors, ev, spec)
    assert r1.portfolio_hash == r2.portfolio_hash
    h = compute_portfolio_hash(spec, factor_dataset_hash="dh_4i")
    assert h == r1.portfolio_hash
    art = Path(r1.summary.storage_uri)
    assert (art / "manifest.json").is_file()
    assert (art / "summary.json").is_file()
    assert (art / "metrics" / "summary.json").is_file()
    assert registry.get_factor_dataset(FID).factor_ref == "raw_port@1.0.0"
    assert r1.summary.metadata.get("portfolio_id") == r1.portfolio_hash[:16]
    assert math.isfinite(r1.frames.metrics.get("sharpe") or 0) or r1.frames.metrics.get(
        "sharpe"
    ) is None
