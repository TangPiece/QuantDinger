"""Phase 4D：IC / RankIC / ICIR 验收。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

from app.services.research_data.factor_lab.metrics import (
    FactorMetricsService,
    MetricSpec,
    compute_metric_hash,
)
from app.services.research_data.factor_lab.metrics.calculators import (
    CrossSectionalICEngine,
    PearsonICCalculator,
)
from app.services.research_data.factor_lab.metrics.aggregator import ICStatisticsAggregator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_lab_metrics.golden import (  # noqa: E402
    D1,
    D2,
    EVAL_HASH,
    constant_factor_panel,
    constant_return_panel,
    default_spec,
    make_env,
    perfect_rank_panel,
    tiny_panel,
    with_missing_panel,
)


def _run(svc, records, spec=None, **meta):
    spec = spec or default_spec()
    return svc.run(
        EVAL_HASH,
        spec,
        metadata={
            "evaluation_records": records,
            "force_recompute": True,
            **meta,
        },
    )


def test_pearson_and_spearman_correctness(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(svc, perfect_rank_panel())
    pts = {(p.evaluation_date, p.horizon): p for p in r.timeseries.points}
    p1 = pts[(D1, 1)]
    p2 = pts[(D2, 1)]
    assert p1.valid and p2.valid
    assert abs(p1.rank_ic - 1.0) < 1e-9
    assert abs(p2.rank_ic - (-1.0)) < 1e-9
    assert p1.ic is not None and p1.ic > 0
    assert p2.ic is not None and p2.ic < 0


def test_icir_tstat_positive_ratio(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(svc, perfect_rank_panel())
    s1 = next(x for x in r.summaries if x.horizon == 1)
    # 两日 IC：正 + 负；mean 可能接近 0；rank_ic mean = 0
    assert s1.valid_day_count == 2
    assert s1.total_day_count == 2
    assert s1.std_ic is not None and s1.std_ic > 0
    assert s1.ic_ir is not None
    assert s1.ic_t_stat is not None
    assert abs(s1.positive_ic_ratio - 0.5) < 1e-9
    assert abs(s1.mean_rank_ic - 0.0) < 1e-9
    assert abs(s1.rank_ic_ir) < 1e-9 or s1.rank_ic_ir is None or abs(s1.mean_rank_ic) < 1e-12
    # RankICIR: mean=0 → IR=0 if std>0
    assert s1.std_rank_ic is not None
    assert abs(s1.rank_ic_ir or 0.0) < 1e-9


def test_cross_sectional_not_pooled():
    """全局 concat 的 corr 与按日 mean IC 不同。"""
    engine = CrossSectionalICEngine()
    records = perfect_rank_panel()
    series = engine.calculate(
        records, default_spec(horizons=[1]), metric_hash="x"
    )
    daily = [p.ic for p in series.points if p.horizon == 1 and p.valid]
    mean_daily = sum(daily) / len(daily)
    # 池化
    xs = [r["factor_value"] for r in records]
    ys = [r["forward_return_1d"] for r in records]
    pooled = PearsonICCalculator().day_corr(xs, ys)
    assert pooled is not None
    # 日均 IC ≈ 0；池化因两日混合不为 0 或至少与日均不同路径存在
    assert abs(mean_daily) < abs(pooled) or abs(mean_daily - pooled) > 1e-6


def test_multi_horizon(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(svc, perfect_rank_panel())
    hs = {s.horizon for s in r.summaries}
    assert hs == {1, 5}
    assert all(s.valid_day_count == 2 for s in r.summaries)


def test_min_cross_section_threshold(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        tiny_panel(),
        default_spec(horizons=[1], min_cross_section_size=30),
    )
    assert r.timeseries.points
    assert all(not p.valid for p in r.timeseries.points)
    assert all(p.ic is None for p in r.timeseries.points)


def test_constant_factor_and_return():
    engine = CrossSectionalICEngine()
    for panel in (constant_factor_panel(), constant_return_panel()):
        series = engine.calculate(
            panel,
            MetricSpec(
                evaluation_hash=EVAL_HASH,
                horizons=[1],
                min_cross_section_size=3,
            ),
            metric_hash="c",
        )
        assert series.points[0].ic is None
        assert series.points[0].rank_ic is None
        assert not series.points[0].valid


def test_missing_filtered(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(svc, with_missing_panel(), default_spec(horizons=[1]))
    p = next(x for x in r.timeseries.points if x.evaluation_date == D1)
    # 仅 A/B/C 三只 VALID；D/E 被 status 过滤
    assert p.sample_count == 3
    assert p.valid


def test_no_date_overlap_empty(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        [
            {
                "instrument_key": "CNStock:A",
                "factor_date": D1,
                "factor_value": 1.0,
                "forward_return_1d": None,
                "sample_status": "VALID",
            }
        ],
        default_spec(horizons=[1], min_cross_section_size=2),
    )
    # sample_count 可能为 0 → invalid
    assert r.timeseries.points
    assert not r.timeseries.points[0].valid


def test_direction_no_abs(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(svc, perfect_rank_panel())
    neg = next(
        p
        for p in r.timeseries.points
        if p.evaluation_date == D2 and p.horizon == 1
    )
    assert neg.ic is not None and neg.ic < 0
    assert neg.rank_ic == pytest.approx(-1.0)


def test_metric_hash_determinism_and_repro(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, svc = make_env(tmp_path)
    spec = default_spec()
    h1 = compute_metric_hash(spec)
    h2 = compute_metric_hash(spec)
    assert h1 == h2
    a = _run(svc, perfect_rank_panel(), spec)
    b = _run(svc, perfect_rank_panel(), spec)
    assert a.metric_hash == b.metric_hash == h1
    assert a.summaries[0].mean_ic == b.summaries[0].mean_ic
    got = registry.get_factor_evaluation_summary(h1, 1)
    assert got.evaluation_hash == EVAL_HASH


def test_schema_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, _, svc = make_env(tmp_path)
    r = _run(svc, perfect_rank_panel())
    uri = r.summaries[0].storage_uri
    assert uri
    man = Path(uri) / "manifest.json"
    summary = Path(uri) / "summary.json"
    assert man.is_file() and summary.is_file()


def test_aggregator_ddof():
    """手工验证 ICIR = mean/stdev(ddof=1)。"""
    from app.services.research_data.factor_lab.metrics.protocol import (
        MetricPoint,
        MetricTimeSeries,
    )

    pts = [
        MetricPoint(evaluation_date=D1, horizon=1, ic=0.1, rank_ic=0.1, sample_count=30, valid=True),
        MetricPoint(evaluation_date=D2, horizon=1, ic=0.3, rank_ic=0.3, sample_count=30, valid=True),
    ]
    series = MetricTimeSeries(
        metric_hash="m", evaluation_hash=EVAL_HASH, horizons=[1], points=pts
    )
    agg = ICStatisticsAggregator().aggregate(series, default_spec(horizons=[1]))
    s = agg[0]
    assert abs(s.mean_ic - 0.2) < 1e-12
    # sample std of [0.1, 0.3] = sqrt(0.02) ≈ 0.14142
    expected_std = math.sqrt(0.02)
    assert abs(s.std_ic - expected_std) < 1e-9
    assert abs(s.ic_ir - (0.2 / expected_std)) < 1e-9
    assert abs(s.ic_t_stat - (0.2 / (expected_std / math.sqrt(2)))) < 1e-9
