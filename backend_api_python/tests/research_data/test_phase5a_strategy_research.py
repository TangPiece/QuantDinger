"""Phase 5A：Strategy Research Foundation 验收。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.research_data.contracts import (
    FactorPortfolioSummary,
    Signal,
)
from app.services.research_data.strategy_research import (
    LookAheadError,
    RebalanceRule,
    StrategyResearchError,
    assert_no_lookahead,
    compute_strategy_hash,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategy_research_golden.golden import (  # noqa: E402
    CODE,
    FID,
    PHASH,
    default_spec,
    factor_panel,
    make_env,
    portfolio_positions,
    run_materialize,
)


def test_signals_and_pit_times(tmp_path):
    _, registry, svc = make_env(tmp_path)
    factors = factor_panel(20, days=3)
    positions = portfolio_positions(20, days=3)
    r = run_materialize(svc, factors, positions)
    assert len(r.frames.signals) == len(factors)
    for s in r.frames.signals:
        assert s.execution_time > s.knowledge_time
        assert s.rank is not None and s.rank >= 1
    # 高分票 rank 更靠前
    day = factors[0]["trading_date"].isoformat()
    day_sigs = [s for s in r.frames.signals if s.trading_date == day]
    top = max(day_sigs, key=lambda s: s.score)
    bot = min(day_sigs, key=lambda s: s.score)
    assert top.rank < bot.rank
    assert registry.get_strategy_research(r.strategy_hash)
    assert registry.get_research_strategy(CODE)


def test_bind_positions_preserve_weights(tmp_path):
    _, _, svc = make_env(tmp_path)
    factors = factor_panel(20, days=2)
    positions = portfolio_positions(20, days=2, top=4)
    r = run_materialize(svc, factors, positions)
    assert len(r.frames.positions) == len(positions)
    wsum = {}
    for p in r.frames.positions:
        wsum.setdefault(p.trading_date, 0.0)
        wsum[p.trading_date] += float(p.target_weight or 0)
    for s in wsum.values():
        assert abs(s - 1.0) < 1e-9
    assert r.frames.positions[0].portfolio_id == r.strategy_hash[:16]


def test_factor_dataset_mismatch(tmp_path):
    _, registry, svc = make_env(tmp_path)
    registry.upsert_factor_portfolio(
        FactorPortfolioSummary(
            portfolio_hash="bad_port",
            factor_dataset_id="other_fid",
            rebalance_frequency="DAILY",
        )
    )
    with pytest.raises(StrategyResearchError, match="factor_dataset_id"):
        run_materialize(
            svc,
            factor_panel(),
            portfolio_positions(),
            default_spec(portfolio_hash="bad_port"),
        )


def test_rebalance_frequency_mismatch(tmp_path):
    _, _, svc = make_env(tmp_path)
    with pytest.raises(StrategyResearchError, match="rebalance frequency"):
        run_materialize(
            svc,
            factor_panel(),
            portfolio_positions(),
            default_spec(rebalance_rule=RebalanceRule(frequency="WEEKLY")),
        )


def test_lookahead_hard_fail():
    bad = Signal(
        signal_id="x",
        instrument_key="CNStock:001",
        trading_date="2024-09-02",
        direction="LONG",
        score=1.0,
        signal_time=datetime(2024, 9, 2, 7, 0, tzinfo=timezone.utc),
        knowledge_time=datetime(2024, 9, 2, 7, 0, tzinfo=timezone.utc),
        # 故意：执行不晚于 knowledge
        execution_time=datetime(2024, 9, 2, 7, 0, tzinfo=timezone.utc),
        strategy_version="t",
        dataset_hash="h",
    )
    with pytest.raises(LookAheadError):
        assert_no_lookahead([bad])


def test_hash_repro_manifest_immutable(tmp_path):
    _, registry, svc = make_env(tmp_path)
    factors = factor_panel(20, days=2)
    positions = portfolio_positions(20, days=2)
    spec = default_spec()
    r1 = run_materialize(svc, factors, positions, spec)
    r2 = run_materialize(svc, factors, positions, spec)
    assert r1.strategy_hash == r2.strategy_hash
    h = compute_strategy_hash(spec, factor_dataset_hash="dh_5a")
    assert h == r1.strategy_hash
    art = Path(r1.summary.storage_uri)
    assert (art / "manifest.json").is_file()
    assert (art / "summary.json").is_file()
    assert (art / "snapshots" / "strategy_spec.json").is_file()
    assert registry.get_factor_dataset(FID).factor_ref == "raw_strat@1.0.0"
    assert registry.get_factor_portfolio(PHASH).portfolio_hash == PHASH
