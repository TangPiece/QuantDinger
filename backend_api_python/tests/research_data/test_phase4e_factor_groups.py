"""Phase 4E：Group Return / Turnover / Cost 验收。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

from app.services.research_data.contracts import EvaluationDatasetRecord
from app.services.research_data.factor_lab.groups import (
    CostModelSpec,
    FactorGroupEvaluationError,
    GroupSpec,
    compute_group_evaluation_hash,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_lab_groups.golden import (  # noqa: E402
    D1,
    D2,
    EVAL_HASH,
    default_spec,
    four_stock_panel,
    make_env,
    tied_panel,
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


def test_two_group_returns_and_long_short(tmp_path):
    """4 股 2 组：Q1=(4%+3%)/2=3.5%，Q2=1.5%，LS=2%。"""
    _, _, svc = make_env(tmp_path)
    r = _run(svc, four_stock_panel(), default_spec(horizons=[1]))
    day1 = [
        x
        for x in r.frames.returns
        if x.evaluation_date == D1 and x.horizon == 1
    ]
    by_g = {x.group: x for x in day1}
    assert abs(by_g[1].group_return - 0.035) < 1e-12
    assert abs(by_g[2].group_return - 0.015) < 1e-12
    assert abs(by_g[1].long_short_return - 0.02) < 1e-12
    assert by_g[1].sample_count == 2


def test_ten_group_runs(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        four_stock_panel(),
        default_spec(group_count=10, horizons=[1], min_cross_section_size=4),
    )
    assert r.frames.membership
    assert any(x.group_return is not None for x in r.frames.returns)


def test_negative_direction(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        four_stock_panel(),
        default_spec(direction="NEGATIVE", horizons=[1]),
    )
    day1 = next(
        x
        for x in r.frames.returns
        if x.evaluation_date == D1 and x.horizon == 1 and x.group == 1
    )
    # NEGATIVE: Long=G2=0.015, Short=G1=0.035, LS=-0.02
    assert abs(day1.long_return - 0.015) < 1e-12
    assert abs(day1.short_return - 0.035) < 1e-12
    assert abs(day1.long_short_return - (-0.02)) < 1e-12


def test_auto_direction_requires_resolve(tmp_path):
    _, registry, svc = make_env(tmp_path)
    # 清空 evaluation metadata → AUTO 无法解析
    registry.upsert_evaluation_dataset(
        EvaluationDatasetRecord(
            evaluation_hash=EVAL_HASH,
            factor_dataset_id="fds_4e",
            factor_dataset_hash="ds_4e",
            snapshot_id="snap_4e",
            metadata={},
        )
    )
    with pytest.raises(FactorGroupEvaluationError):
        _run(
            svc,
            four_stock_panel(),
            GroupSpec(
                evaluation_hash=EVAL_HASH,
                group_count=2,
                direction="AUTO",
                horizons=[1],
                min_cross_section_size=4,
            ),
        )
    # 显式注入 resolved_direction
    r = _run(
        svc,
        four_stock_panel(),
        GroupSpec(
            evaluation_hash=EVAL_HASH,
            group_count=2,
            direction="AUTO",
            horizons=[1],
            min_cross_section_size=4,
        ),
        resolved_direction="POSITIVE",
    )
    assert r.direction == "POSITIVE"


def test_turnover_first_day_nan_and_later(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(svc, four_stock_panel(), default_spec(horizons=[1]))
    t0 = next(
        t
        for t in r.frames.turnover
        if t.evaluation_date == D1
        and t.horizon == 1
        and t.portfolio == "LONG_SHORT"
    )
    t1 = next(
        t
        for t in r.frames.turnover
        if t.evaluation_date == D2
        and t.horizon == 1
        and t.portfolio == "LONG_SHORT"
    )
    assert t0.turnover is None
    assert t1.turnover is not None and t1.turnover > 0


def test_fixed_bps_cost(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        four_stock_panel(),
        default_spec(
            horizons=[1],
            cost_model=CostModelSpec(
                kind="FIXED_BPS", buy_cost_bps=10, sell_cost_bps=10
            ),
        ),
    )
    d2 = next(
        x
        for x in r.frames.returns
        if x.evaluation_date == D2 and x.horizon == 1 and x.group == 1
    )
    assert d2.estimated_cost is not None and d2.estimated_cost > 0
    assert d2.net_long_short_return is not None
    assert abs(
        d2.net_long_short_return - (d2.long_short_return - d2.estimated_cost)
    ) < 1e-12


def test_ties_deterministic(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        tied_panel(),
        default_spec(group_count=2, horizons=[1], min_cross_section_size=4),
    )
    # 不应崩溃；membership 有 4 行
    mem = [m for m in r.frames.membership if m.horizon == 1]
    assert len(mem) == 4
    # D 因子最高 → group 1
    d_mem = next(m for m in mem if m.instrument_key == "CNStock:D")
    assert d_mem.group == 1


def test_min_cross_section(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(
        svc,
        four_stock_panel(),
        default_spec(horizons=[1], min_cross_section_size=30),
    )
    assert r.frames.membership == []
    assert r.summaries[0].valid_day_count == 0


def test_multi_horizon(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(svc, four_stock_panel())
    assert {s.horizon for s in r.summaries} == {1, 5}


def test_hash_repro_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, svc = make_env(tmp_path)
    spec = default_spec()
    h = compute_group_evaluation_hash(spec, resolved_direction="POSITIVE")
    a = _run(svc, four_stock_panel(), spec)
    b = _run(svc, four_stock_panel(), spec)
    assert a.group_evaluation_hash == b.group_evaluation_hash == h
    assert a.summaries[0].mean_long_short_return == b.summaries[0].mean_long_short_return
    uri = Path(a.summaries[0].storage_uri)
    assert (uri / "manifest.json").is_file()
    assert (uri / "summary.json").is_file()
    got = registry.get_factor_group_evaluation(h, 1)
    assert got.evaluation_hash == EVAL_HASH


def test_membership_schema_fields(tmp_path):
    _, _, svc = make_env(tmp_path)
    r = _run(svc, four_stock_panel(), default_spec(horizons=[1]))
    m = r.frames.membership[0]
    assert m.weight > 0
    assert m.factor_rank > 0
    assert 1 <= m.group <= 2
