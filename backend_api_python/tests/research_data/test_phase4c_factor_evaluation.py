"""Phase 4C：Factor Evaluation Foundation 验收。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

from app.services.research_data.factor_lab.evaluation import (
    EvaluationSpec,
    ForwardReturnEngine,
    ReturnSpec,
    build_evaluation_plan,
    compute_evaluation_hash,
    shift_trading_day,
)
from app.services.research_data.factor_lab.evaluation.forward_return import (
    ForwardReturnEngine as FRE,
)
from app.services.research_data.factor_lab.evaluation.planner import EvaluationPlanError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_lab_evaluation.golden import (  # noqa: E402
    INSTRUMENTS,
    SNAP_A,
    SNAP_B,
    UNIVERSE,
    default_spec,
    factor_records,
    make_env,
)


def _meta(days, **kw):
    base = {
        "factor_records": factor_records(days),
        "instruments": INSTRUMENTS,
        "universe_members": {"CNStock:AAA", "CNStock:BBB"},
    }
    base.update(kw)
    return base


def test_forward_return_correctness(tmp_path):
    """手工价：AAA day0 close=100 open_d1=100.5 → next_open_to_close 1d。"""
    _, _, _, svc, days, _, _ = make_env(tmp_path)
    # day0 factor → entry day1 open 100.5 → exit day1 close 102
    # return_1d = 102/100.5 - 1
    engine = ForwardReturnEngine()
    cal = days
    market_idx = {
        ("CNStock:AAA", days[0]): {"open": 99.0, "close": 100.0},
        ("CNStock:AAA", days[1]): {"open": 100.5, "close": 102.0},
        ("CNStock:AAA", days[5]): {"open": 108.5, "close": 110.0},
    }
    # 补齐日历中间日占位
    for d in days[2:5]:
        market_idx.setdefault(("CNStock:AAA", d), {"open": 1.0, "close": 1.0})
    rs = ReturnSpec(
        definition="next_open_to_close", horizons=[1, 5], execution_delay=1
    )
    out = engine.compute_row_returns(
        market_by_key_date=market_idx,
        calendar=cal,
        instrument_key="CNStock:AAA",
        factor_date=days[0],
        return_spec=rs,
    )
    assert out["entry_date"] == days[1]
    assert abs(out["returns"]["forward_return_1d"] - (102.0 / 100.5 - 1.0)) < 1e-9
    # horizon 5: exit=days[5] close 110 / entry 100.5
    assert abs(out["returns"]["forward_return_5d"] - (110.0 / 100.5 - 1.0)) < 1e-9


def test_multi_horizon_and_close_to_close():
    cal = [date(2024, 5, 6 + i) for i in range(10) if (date(2024, 5, 6 + i).weekday() < 5)]
    # 简化：用连续工作日列表
    days = []
    d = date(2024, 5, 6)
    while len(days) < 8:
        if d.weekday() < 5:
            days.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    prices = {
        (days[i]): {"open": 10 + i, "close": 100 + i} for i in range(len(days))
    }
    midx = {("X", day): prices[day] for day in days}
    rs = ReturnSpec(definition="close_to_close", horizons=[1, 5], execution_delay=0)
    out = FRE().compute_row_returns(
        market_by_key_date=midx,
        calendar=days,
        instrument_key="X",
        factor_date=days[0],
        return_spec=rs,
    )
    # delay=0 entry=days[0] close 100; exit day1 close 101 → 0.01
    assert abs(out["returns"]["forward_return_1d"] - 0.01) < 1e-9
    assert abs(out["returns"]["forward_return_5d"] - (105.0 / 100.0 - 1.0)) < 1e-9


def test_execution_delay(tmp_path):
    _, _, _, svc, days, _, _ = make_env(tmp_path)
    # 用 BBB 避开 AAA 停牌日；并清空 suspended 注入以免干扰
    meta = _meta(days, suspended=set())
    results = {}
    for delay in (0, 1, 2):
        spec = default_spec(days)
        spec = spec.model_copy(
            update={
                "return_spec": ReturnSpec(
                    definition="close_to_close",
                    horizons=[5],
                    execution_delay=delay,
                )
            }
        )
        r = svc.run(spec, metadata={**meta, "force_recompute": True})
        bbb = [
            x
            for x in r.frame.records
            if x["instrument_key"] == "CNStock:BBB"
            and x["factor_date"] == days[0]
            and x["sample_status"] == "VALID"
        ]
        assert bbb, f"delay={delay} statuses={[x['sample_status'] for x in r.frame.records if x['instrument_key']=='CNStock:BBB' and x['factor_date']==days[0]]}"
        results[delay] = (bbb[0]["entry_date"], bbb[0].get("forward_return_5d"))
    assert results[0][0] == days[0]
    assert results[1][0] == days[1]
    assert results[2][0] == days[2]
    assert results[0][1] != results[1][1]


def test_trading_calendar_shift():
    days = []
    d = date(2024, 5, 3)  # Friday
    while len(days) < 5:
        if d.weekday() < 5:
            days.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    # Friday + 1 trading day = Monday
    nxt = shift_trading_day(days, days[0], 1)
    assert nxt.weekday() == 0


def test_suspended_stock(tmp_path):
    _, _, _, svc, days, sus_day, _ = make_env(tmp_path)
    # factor on day before suspension with delay=1 → entry on sus_day
    # 找 sus_day 的前一交易日
    idx = days.index(sus_day)
    factor_day = days[idx - 1]
    meta = _meta(
        days,
        suspended={("CNStock:AAA", sus_day)},
        factor_records=[
            {
                "instrument_key": "CNStock:AAA",
                "factor_date": factor_day,
                "factor_value": 0.5,
            },
            {
                "instrument_key": "CNStock:BBB",
                "factor_date": factor_day,
                "factor_value": 0.2,
            },
        ],
    )
    spec = default_spec(days)
    r = svc.run(spec, metadata=meta)
    aaa = [
        x
        for x in r.frame.records
        if x["instrument_key"] == "CNStock:AAA" and x["factor_date"] == factor_day
    ]
    assert aaa and aaa[0]["sample_status"] == "SUSPENDED"
    assert aaa[0].get("forward_return_1d") is None


def test_missing_data(tmp_path):
    _, _, _, svc, days, _, _ = make_env(tmp_path)
    meta = _meta(
        days,
        factor_records=[
            {
                "instrument_key": "CNStock:AAA",
                "factor_date": days[0],
                "factor_value": float("nan"),
            },
            {
                "instrument_key": "CNStock:BBB",
                "factor_date": days[0],
                "factor_value": 0.1,
            },
        ],
    )
    r = svc.run(default_spec(days), metadata=meta)
    statuses = {x["instrument_key"]: x["sample_status"] for x in r.frame.records}
    assert statuses["CNStock:AAA"] == "MISSING_FACTOR"
    assert statuses["CNStock:BBB"] in ("VALID", "MISSING_RETURN")


def test_pit_leakage(tmp_path):
    _, _, _, svc, days, _, _ = make_env(tmp_path)
    meta = _meta(
        days,
        pit_invalid={("CNStock:AAA", days[0])},
        factor_records=[
            {
                "instrument_key": "CNStock:AAA",
                "factor_date": days[0],
                "factor_value": 0.9,
                "pit_invalid": True,
            },
            {
                "instrument_key": "CNStock:BBB",
                "factor_date": days[0],
                "factor_value": 0.1,
            },
        ],
    )
    r = svc.run(default_spec(days), metadata=meta)
    aaa = [x for x in r.frame.records if x["instrument_key"] == "CNStock:AAA"][0]
    assert aaa["sample_status"] == "PIT_INVALID"


def test_universe_snapshot(tmp_path):
    _, _, _, svc, days, _, _ = make_env(tmp_path)
    # 2020 snapshot: AAA in；2026: AAA out
    meta_a = _meta(
        days,
        universe_members={"CNStock:AAA", "CNStock:BBB"},
        factor_records=factor_records(days, include_ccc=True),
    )
    ra = svc.run(default_spec(days, snapshot_id=SNAP_A), metadata=meta_a)
    aaa_a = [
        x
        for x in ra.frame.records
        if x["instrument_key"] == "CNStock:AAA" and x["factor_date"] == days[0]
    ]
    assert aaa_a and aaa_a[0]["sample_status"] == "VALID"

    meta_b = {
        "factor_records": factor_records(days, include_ccc=True),
        "instruments": INSTRUMENTS,
        "universe_members": {"CNStock:BBB", "CNStock:CCC"},
        "force_recompute": True,
    }
    rb = svc.run(default_spec(days, snapshot_id=SNAP_B), metadata=meta_b)
    aaa_b = [
        x
        for x in rb.frame.records
        if x["instrument_key"] == "CNStock:AAA" and x["factor_date"] == days[0]
    ]
    assert aaa_b and aaa_b[0]["sample_status"] == "OUT_OF_UNIVERSE"
    assert ra.record.evaluation_hash != rb.record.evaluation_hash


def test_universe_requires_snapshot(tmp_path):
    _, registry, _, _, days, _, fds = make_env(tmp_path)
    with pytest.raises(EvaluationPlanError):
        build_evaluation_plan(
            EvaluationSpec(
                factor_dataset_id=fds.factor_dataset_id,
                universe_code=UNIVERSE,
                snapshot_id="",
                start_date=days[0].isoformat(),
                end_date=days[5].isoformat(),
            ),
            fds,
        )


def test_no_lookahead(tmp_path):
    _, _, _, svc, days, _, _ = make_env(tmp_path)
    r = svc.run(default_spec(days), metadata=_meta(days))
    for row in r.frame.records:
        if row["sample_status"] != "VALID":
            continue
        fd = row["factor_date"]
        ed = row["entry_date"]
        xd = row["exit_date"]
        assert fd < ed <= xd


def test_hash_determinism_and_repro(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, _, svc, days, _, fds = make_env(tmp_path)
    spec = default_spec(days)
    h1 = compute_evaluation_hash(spec, factor_dataset_hash=fds.dataset_hash)
    h2 = compute_evaluation_hash(spec, factor_dataset_hash=fds.dataset_hash)
    assert h1 == h2
    meta = _meta(days)
    a = svc.run(spec, metadata=meta)
    b = svc.run(spec, metadata=meta)
    assert a.record.evaluation_hash == b.record.evaluation_hash == h1
    assert a.record.row_count == b.record.row_count
    assert a.frame.row_count > 0


def test_schema_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, _, svc, days, _, _ = make_env(tmp_path)
    r = svc.run(default_spec(days), metadata=_meta(days))
    assert r.record.checksum
    assert r.record.storage_uri
    got = registry.get_evaluation_dataset(r.record.evaluation_hash)
    assert got.factor_dataset_id == r.record.factor_dataset_id
    man = Path(got.storage_uri) / "manifest.json"
    assert man.is_file()
    # 行含必需列
    row = next(x for x in r.frame.records if x["sample_status"] == "VALID")
    for col in (
        "instrument_key",
        "factor_date",
        "factor_value",
        "entry_date",
        "exit_date",
        "sample_status",
        "forward_return_1d",
        "forward_return_5d",
    ):
        assert col in row
