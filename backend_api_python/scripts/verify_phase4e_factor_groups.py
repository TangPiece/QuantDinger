#!/usr/bin/env python3
"""Phase 4E 验收：Group Return / Turnover / Cost。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4e_factor_groups.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.research_data.factor_lab.groups import (
        CostModelSpec,
        compute_group_evaluation_hash,
    )
    from factor_lab_groups.golden import (
        D1,
        D2,
        EVAL_HASH,
        default_spec,
        four_stock_panel,
        make_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4e_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    def run(records, spec=None, **meta):
        return svc.run(
            EVAL_HASH,
            spec or default_spec(),
            metadata={
                "evaluation_records": records,
                "force_recompute": True,
                **meta,
            },
        )

    r = run(four_stock_panel(), default_spec(horizons=[1]))
    day1 = {
        x.group: x
        for x in r.frames.returns
        if x.evaluation_date == D1 and x.horizon == 1
    }
    checks["group_return_ls"] = (
        abs(day1[1].group_return - 0.035) < 1e-12
        and abs(day1[1].long_short_return - 0.02) < 1e-12
    )

    r_neg = run(
        four_stock_panel(), default_spec(direction="NEGATIVE", horizons=[1])
    )
    neg = next(
        x
        for x in r_neg.frames.returns
        if x.evaluation_date == D1 and x.horizon == 1 and x.group == 1
    )
    checks["negative_direction"] = abs(neg.long_short_return - (-0.02)) < 1e-12

    t0 = next(
        t
        for t in r.frames.turnover
        if t.evaluation_date == D1 and t.portfolio == "LONG_SHORT"
    )
    t1 = next(
        t
        for t in r.frames.turnover
        if t.evaluation_date == D2 and t.portfolio == "LONG_SHORT"
    )
    checks["turnover"] = t0.turnover is None and (t1.turnover or 0) > 0

    r_cost = run(
        four_stock_panel(),
        default_spec(
            horizons=[1],
            cost_model=CostModelSpec(kind="FIXED_BPS", buy_cost_bps=10, sell_cost_bps=10),
        ),
    )
    d2 = next(
        x
        for x in r_cost.frames.returns
        if x.evaluation_date == D2 and x.horizon == 1 and x.group == 1
    )
    checks["cost"] = (
        d2.estimated_cost is not None
        and d2.estimated_cost > 0
        and d2.net_long_short_return is not None
    )

    r10 = run(
        four_stock_panel(),
        default_spec(group_count=10, horizons=[1]),
    )
    checks["ten_group"] = bool(r10.frames.membership)

    r_mh = run(four_stock_panel())
    checks["multi_horizon"] = {s.horizon for s in r_mh.summaries} == {1, 5}

    spec = default_spec()
    h = compute_group_evaluation_hash(spec, resolved_direction="POSITIVE")
    a = run(four_stock_panel(), spec)
    b = run(four_stock_panel(), spec)
    checks["hash_repro"] = (
        a.group_evaluation_hash == b.group_evaluation_hash == h
        and a.summaries[0].mean_long_short_return
        == b.summaries[0].mean_long_short_return
    )

    uri = Path(a.summaries[0].storage_uri or "")
    checks["manifest"] = (uri / "manifest.json").is_file() and (
        uri / "summary.json"
    ).is_file()
    checks["registry"] = (
        registry.get_factor_group_evaluation(h, 1).group_evaluation_hash == h
    )

    all_ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": all_ok,
                "checks": checks,
                "group_evaluation_hash": h,
                "mean_ls_1d": a.summaries[0].mean_long_short_return,
                "mean_turnover": a.summaries[0].mean_turnover,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
