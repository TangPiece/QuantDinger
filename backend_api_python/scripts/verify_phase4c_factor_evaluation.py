#!/usr/bin/env python3
"""Phase 4C 验收：Factor Evaluation Foundation。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4c_factor_evaluation.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.research_data.contracts import PricePolicy
    from app.services.research_data.factor_lab.evaluation import (
        EvaluationSpec,
        ForwardReturnEngine,
        ReturnSpec,
        build_evaluation_plan,
        compute_evaluation_hash,
        shift_trading_day,
    )
    from app.services.research_data.factor_lab.evaluation.planner import (
        EvaluationPlanError,
    )
    from factor_lab_evaluation.golden import (
        INSTRUMENTS,
        SNAP_A,
        SNAP_B,
        UNIVERSE,
        default_spec,
        factor_records,
        make_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4c_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, _, svc, days, sus_day, fds = make_env(tmp)

    checks: dict[str, bool] = {}

    def meta(**kw):
        base = {
            "factor_records": factor_records(days),
            "instruments": INSTRUMENTS,
            "universe_members": {"CNStock:AAA", "CNStock:BBB"},
        }
        base.update(kw)
        return base

    # 1–2) forward return + multi-horizon
    engine = ForwardReturnEngine()
    midx = {
        ("CNStock:AAA", days[0]): {"open": 99.0, "close": 100.0},
        ("CNStock:AAA", days[1]): {"open": 100.5, "close": 102.0},
        ("CNStock:AAA", days[5]): {"open": 108.5, "close": 110.0},
    }
    for d in days[2:5]:
        midx.setdefault(("CNStock:AAA", d), {"open": 1.0, "close": 1.0})
    out = engine.compute_row_returns(
        market_by_key_date=midx,
        calendar=days,
        instrument_key="CNStock:AAA",
        factor_date=days[0],
        return_spec=ReturnSpec(
            definition="next_open_to_close", horizons=[1, 5], execution_delay=1
        ),
    )
    checks["forward_return"] = (
        abs(out["returns"]["forward_return_1d"] - (102.0 / 100.5 - 1.0)) < 1e-9
        and abs(out["returns"]["forward_return_5d"] - (110.0 / 100.5 - 1.0)) < 1e-9
    )

    # 3) execution delay
    delay_ok = True
    entries = {}
    for delay in (0, 1, 2):
        spec = default_spec(days).model_copy(
            update={
                "return_spec": ReturnSpec(
                    definition="close_to_close",
                    horizons=[5],
                    execution_delay=delay,
                )
            }
        )
        r = svc.run(
            spec, metadata=meta(suspended=set(), force_recompute=True)
        )
        row = next(
            x
            for x in r.frame.records
            if x["instrument_key"] == "CNStock:BBB"
            and x["factor_date"] == days[0]
            and x["sample_status"] == "VALID"
        )
        entries[delay] = row["entry_date"]
    delay_ok = (
        entries[0] == days[0]
        and entries[1] == days[1]
        and entries[2] == days[2]
    )
    checks["execution_delay"] = delay_ok

    # 4) trading calendar
    fri = date(2024, 5, 3)
    cal = []
    d = fri
    while len(cal) < 5:
        if d.weekday() < 5:
            cal.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    checks["trading_calendar"] = shift_trading_day(cal, cal[0], 1).weekday() == 0

    # 5) suspended
    idx = days.index(sus_day)
    factor_day = days[idx - 1]
    r_sus = svc.run(
        default_spec(days),
        metadata=meta(
            force_recompute=True,
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
        ),
    )
    aaa_sus = next(
        x
        for x in r_sus.frame.records
        if x["instrument_key"] == "CNStock:AAA" and x["factor_date"] == factor_day
    )
    checks["suspended"] = (
        aaa_sus["sample_status"] == "SUSPENDED"
        and aaa_sus.get("forward_return_1d") is None
    )

    # 6) missing
    r_miss = svc.run(
        default_spec(days),
        metadata=meta(
            force_recompute=True,
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
        ),
    )
    st = {x["instrument_key"]: x["sample_status"] for x in r_miss.frame.records}
    checks["missing_data"] = st.get("CNStock:AAA") == "MISSING_FACTOR"

    # 7) PIT
    r_pit = svc.run(
        default_spec(days),
        metadata=meta(
            force_recompute=True,
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
        ),
    )
    checks["pit_leakage"] = any(
        x["sample_status"] == "PIT_INVALID" for x in r_pit.frame.records
    )

    # 8) universe snapshot
    ra = svc.run(
        default_spec(days, snapshot_id=SNAP_A),
        metadata=meta(force_recompute=True),
    )
    rb = svc.run(
        default_spec(days, snapshot_id=SNAP_B),
        metadata={
            "factor_records": factor_records(days, include_ccc=True),
            "instruments": INSTRUMENTS,
            "universe_members": {"CNStock:BBB", "CNStock:CCC"},
            "force_recompute": True,
        },
    )
    aaa_b = next(
        x
        for x in rb.frame.records
        if x["instrument_key"] == "CNStock:AAA" and x["factor_date"] == days[0]
    )
    snap_fail = False
    try:
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
    except EvaluationPlanError:
        snap_fail = True
    checks["universe_snapshot"] = (
        aaa_b["sample_status"] == "OUT_OF_UNIVERSE"
        and ra.record.evaluation_hash != rb.record.evaluation_hash
        and snap_fail
    )

    # 9) no look-ahead
    r_main = svc.run(default_spec(days), metadata=meta(force_recompute=True))
    checks["no_lookahead"] = all(
        x["factor_date"] < x["entry_date"] <= x["exit_date"]
        for x in r_main.frame.records
        if x["sample_status"] == "VALID"
    )

    # 10–11) hash + repro
    spec = default_spec(days)
    h = compute_evaluation_hash(spec, factor_dataset_hash=fds.dataset_hash)
    a = svc.run(spec, metadata=meta())
    b = svc.run(spec, metadata=meta())
    checks["hash_repro"] = (
        a.record.evaluation_hash == b.record.evaluation_hash == h
        and a.record.row_count == b.record.row_count
        and a.frame.row_count > 0
    )

    # 12) schema + manifest
    man = Path(a.record.storage_uri or "") / "manifest.json"
    got = registry.get_evaluation_dataset(a.record.evaluation_hash)
    checks["schema_manifest"] = bool(
        a.record.checksum and man.is_file() and got.evaluation_hash == h
    )

    all_ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": all_ok,
                "checks": checks,
                "evaluation_hash": h,
                "row_count": a.record.row_count,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
