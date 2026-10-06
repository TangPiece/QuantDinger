"""Phase 4F：Stability / Decay 验收。"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from statistics import mean

import pytest

from app.services.research_data.factor_lab.stability import (
    FactorStabilityError,
    StabilitySpec,
    compute_stability_hash,
)
from app.services.research_data.factor_lab.stability.rolling import RollingICCalculator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_lab_stability.golden import (  # noqa: E402
    EVAL_HASH,
    START,
    cross_year_panel,
    default_spec,
    make_env,
    make_metric_points,
    multi_day_panel,
)


def _run(svc, records, spec=None, **meta):
    return svc.run(
        EVAL_HASH,
        spec or default_spec(),
        metadata={
            "evaluation_records": records,
            "force_recompute": True,
            **meta,
        },
    )


def test_rolling_ic_trailing_mean(tmp_path):
    """window=3 时第 3 日 ic_mean = 前三日均值。"""
    ics = [0.01, 0.02, 0.03, 0.04, 0.05]
    pts = make_metric_points(n_days=5, ic_seq=ics)
    calc = RollingICCalculator()
    rows = calc.calculate(
        pts,
        default_spec(rolling_windows=[3], min_rolling_samples=3),
    )
    d2 = START + timedelta(days=2)
    row = next(r for r in rows if r.evaluation_date == d2 and r.window == 3)
    assert abs(row.ic_mean - mean(ics[:3])) < 1e-12
    assert abs(row.rankic_mean - mean([x + 0.01 for x in ics[:3]])) < 1e-12
    assert row.sample_count == 3


def test_rolling_no_lookahead(tmp_path):
    """改 T+1 的 IC 不得影响 T 的 rolling。"""
    ics = [0.01, 0.02, 0.03, 0.04, 0.05]
    pts = make_metric_points(n_days=5, ic_seq=ics)
    spec = default_spec(rolling_windows=[3], min_rolling_samples=3)
    calc = RollingICCalculator()
    before = {
        (r.evaluation_date, r.window): r.ic_mean
        for r in calc.calculate(pts, spec)
    }
    # 污染最后一日
    pts[-1].ic = 0.99
    after = {
        (r.evaluation_date, r.window): r.ic_mean
        for r in calc.calculate(pts, spec)
    }
    t = START + timedelta(days=3)  # 倒数第二天
    assert before[(t, 3)] == after[(t, 3)]
    # 末日自身会变
    last = START + timedelta(days=4)
    assert before[(last, 3)] != after[(last, 3)]


def test_insufficient_rolling_samples_null(tmp_path):
    pts = make_metric_points(n_days=2, ic_seq=[0.1, 0.2])
    rows = RollingICCalculator().calculate(
        pts, default_spec(rolling_windows=[5], min_rolling_samples=3)
    )
    assert all(r.ic_mean is None for r in rows)
    assert all(r.sample_count < 3 for r in rows)


def test_end_to_end_decay_and_distribution(tmp_path):
    _, registry, svc = make_env(tmp_path)
    r = _run(svc, multi_day_panel(12), default_spec())
    assert r.frames.decay
    d1 = next(d for d in r.frames.decay if d.horizon == 1)
    d5 = next(d for d in r.frames.decay if d.horizon == 5)
    assert d1.ic_mean is not None and d1.ic_mean > 0.9
    assert d5.ic_mean is not None
    assert d1.long_short_return is not None
    assert any(x.metric == "IC" for x in r.frames.distributions)
    assert r.summaries
    s = registry.get_factor_stability_evaluation(r.stability_hash, 1)
    # 完美相关时 std=0 → ICIR 为 None（与 4D 一致）；此处验 mean / pos_ratio
    assert s.ic_stability_metrics_json.get("ic_mean") == 1.0
    assert s.ic_stability_metrics_json.get("ic_positive_ratio") == 1.0


def test_icir_with_varying_injected_ic(tmp_path):
    """注入非恒定 IC 序列时 ICIR 有定义。"""
    _, registry, svc = make_env(tmp_path)
    ics = [0.02, -0.01, 0.03, 0.04, 0.01, 0.05, -0.02, 0.03]
    pts = make_metric_points(n_days=8, ic_seq=ics)
    r = _run(
        svc,
        multi_day_panel(8),
        default_spec(decay_horizons=[1]),
        metric_points=pts,
    )
    s = registry.get_factor_stability_evaluation(r.stability_hash, 1)
    assert s.ic_stability_metrics_json.get("ic_ir") is not None
    assert 0 < s.ic_stability_metrics_json.get("ic_positive_ratio") < 1


def test_multi_window_and_group_stability(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        multi_day_panel(12),
        default_spec(rolling_windows=[3, 5, 20]),
    )
    windows = {x.window for x in r.frames.rolling_ic}
    assert {3, 5, 20}.issubset(windows)
    assert any(g.portfolio == "LONG_SHORT" for g in r.frames.group_stability)
    assert any(g.portfolio == "TOP" for g in r.frames.group_stability)


def test_year_quarter_regime(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        cross_year_panel(),
        default_spec(decay_horizons=[1], rolling_windows=[3]),
    )
    years = {
        x.regime_value
        for x in r.frames.regime
        if x.regime_type == "YEAR"
    }
    assert "2023" in years and "2024" in years
    quarters = {
        x.regime_value
        for x in r.frames.regime
        if x.regime_type == "QUARTER"
    }
    assert any(v.endswith("Q4") for v in quarters)
    assert any(v.endswith("Q1") for v in quarters)


def test_hash_deterministic(tmp_path):
    spec = default_spec()
    h1 = compute_stability_hash(spec, resolved_direction="POSITIVE")
    h2 = compute_stability_hash(spec, resolved_direction="POSITIVE")
    assert h1 == h2
    h3 = compute_stability_hash(spec, resolved_direction="NEGATIVE")
    assert h1 != h3


def test_hash_repro_and_manifest(tmp_path):
    _, registry, svc = make_env(tmp_path)
    records = multi_day_panel(10)
    r1 = _run(svc, records, default_spec())
    r2 = _run(svc, records, default_spec())
    assert r1.stability_hash == r2.stability_hash
    art = Path(r1.summaries[0].storage_uri)
    assert (art / "manifest.json").is_file()
    assert (art / "summary.json").is_file()
    assert registry.get_factor_stability_evaluation(r1.stability_hash, 1)


def test_auto_direction_hard_fail(tmp_path):
    store, registry, svc = make_env(tmp_path)
    # 清掉 evaluation metadata direction
    from app.services.research_data.contracts import EvaluationDatasetRecord

    registry.upsert_evaluation_dataset(
        EvaluationDatasetRecord(
            evaluation_hash=EVAL_HASH,
            factor_dataset_id="fds_4f",
            factor_dataset_hash="ds_4f",
            snapshot_id="snap_4f",
            universe_code="CSI300",
            start_date=START.isoformat(),
            end_date=START.isoformat(),
            metadata={},
        )
    )
    with pytest.raises(FactorStabilityError):
        svc.run(
            EVAL_HASH,
            StabilitySpec(
                evaluation_hash=EVAL_HASH,
                direction="AUTO",
                min_cross_section_size=4,
                group_count=2,
                rolling_windows=[3],
                decay_horizons=[1],
                min_rolling_samples=2,
            ),
            metadata={
                "evaluation_records": multi_day_panel(5),
                "force_recompute": True,
            },
        )


def test_injected_metric_points_path(tmp_path):
    _, _, svc = make_env(tmp_path)
    pts = make_metric_points(n_days=8)
    r = _run(
        svc,
        multi_day_panel(8),
        default_spec(decay_horizons=[1]),
        metric_points=pts,
    )
    assert r.frames.rolling_ic
    # 注入序列与引擎无关：首日有效 rolling 需满 min samples
    assert any(x.ic_mean is not None for x in r.frames.rolling_ic)


def test_bull_regime_rejected():
    with pytest.raises(Exception):
        StabilitySpec(
            evaluation_hash=EVAL_HASH,
            regime_types=["BULL"],  # type: ignore[list-item]
        )
