#!/usr/bin/env python3
"""Phase 4I 验收：Factor Portfolio。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4i_factor_portfolio.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.research_data.factor_lab.portfolio import (
        compute_portfolio_hash,
    )
    from factor_lab_portfolio.golden import (
        FID,
        default_spec,
        evaluation_panel,
        factor_panel,
        make_env,
        run_portfolio,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4i_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    factors = factor_panel(40, days=10)
    ev = evaluation_panel(factors)

    r_lo = run_portfolio(
        svc, factors, ev, default_spec(top_pct=0.1)
    )
    by = defaultdict(list)
    for p in r_lo.frames.positions:
        by[p.trading_date].append(p)
    day0 = by[sorted(by.keys())[0]]
    checks["long_only_count"] = len(day0) == 4
    checks["long_only_sum"] = abs(sum(p.weight for p in day0) - 1.0) < 1e-9

    r_ls = run_portfolio(
        svc,
        factors,
        ev,
        default_spec(construction_method="LONG_SHORT", top_pct=0.1),
    )
    day_ls = [
        p
        for p in r_ls.frames.positions
        if p.trading_date == sorted({x.trading_date for x in r_ls.frames.positions})[0]
    ]
    checks["long_short_weights"] = (
        abs(sum(p.weight for p in day_ls if p.leg == "LONG") - 1.0) < 1e-9
        and abs(sum(p.weight for p in day_ls if p.leg == "SHORT") + 1.0) < 1e-9
    )
    checks["ls_metrics"] = (
        r_ls.frames.metrics.get("mean_long_short_return") is not None
    )

    r_q = run_portfolio(
        svc,
        factors,
        evaluation_panel(factor_panel(50, days=5)),
        default_spec(
            construction_method="QUANTILE",
            group_count=5,
            min_cross_section_size=10,
        ),
    )
    legs = {p.leg for p in r_q.frames.positions}
    checks["quantile_legs"] = {"Q1", "Q2", "Q3", "Q4", "Q5"} <= legs

    r_to = run_portfolio(
        svc,
        factors,
        ev,
        default_spec(rebalance_frequency="DAILY", min_turnover=1e9),
    )
    flags = [t.rebalanced for t in r_to.frames.turnover]
    checks["min_turnover_skip"] = flags[0] is True and all(
        f is False for f in flags[1:]
    )

    spec = default_spec()
    h1 = compute_portfolio_hash(spec, factor_dataset_hash="dh_4i")
    h2 = compute_portfolio_hash(spec, factor_dataset_hash="dh_4i")
    checks["hash_repro"] = h1 == h2 == r_lo.portfolio_hash
    art = Path(r_lo.summary.storage_uri)
    checks["manifest"] = (art / "manifest.json").is_file()
    checks["registry"] = bool(registry.get_factor_portfolio(r_lo.portfolio_hash))
    checks["raw_immutable"] = (
        registry.get_factor_dataset(FID).factor_ref == "raw_port@1.0.0"
    )

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "portfolio_hash": r_lo.portfolio_hash,
                "metrics": r_lo.frames.metrics,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
