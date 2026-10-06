#!/usr/bin/env python3
"""Phase 4F 验收：Stability / Decay / Regime。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4f_factor_stability.py
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
    from app.services.research_data.factor_lab.stability import compute_stability_hash
    from app.services.research_data.factor_lab.stability.rolling import (
        RollingICCalculator,
    )
    from factor_lab_stability.golden import (
        EVAL_HASH,
        START,
        cross_year_panel,
        default_spec,
        make_env,
        make_metric_points,
        multi_day_panel,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4f_"))
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

    # Rolling no look-ahead
    ics = [0.01, 0.02, 0.03, 0.04, 0.05]
    pts = make_metric_points(n_days=5, ic_seq=ics)
    calc = RollingICCalculator()
    spec_roll = default_spec(rolling_windows=[3], min_rolling_samples=3)
    before = {
        (r.evaluation_date, r.window): r.ic_mean
        for r in calc.calculate(pts, spec_roll)
    }
    pts[-1].ic = 0.99
    after = {
        (r.evaluation_date, r.window): r.ic_mean
        for r in calc.calculate(pts, spec_roll)
    }
    from datetime import timedelta

    t = START + timedelta(days=3)
    checks["no_lookahead"] = before[(t, 3)] == after[(t, 3)]

    r = run(multi_day_panel(12))
    checks["rolling"] = any(x.ic_mean is not None for x in r.frames.rolling_ic)
    checks["distribution"] = any(x.metric == "IC" for x in r.frames.distributions)
    d1 = next(d for d in r.frames.decay if d.horizon == 1)
    checks["decay"] = d1.ic_mean is not None and d1.long_short_return is not None
    checks["group_stability"] = any(
        g.portfolio == "LONG_SHORT" for g in r.frames.group_stability
    )

    r_reg = run(cross_year_panel(), default_spec(decay_horizons=[1]))
    years = {
        x.regime_value for x in r_reg.frames.regime if x.regime_type == "YEAR"
    }
    checks["year_regime"] = "2023" in years and "2024" in years

    h1 = compute_stability_hash(default_spec(), resolved_direction="POSITIVE")
    h2 = compute_stability_hash(default_spec(), resolved_direction="POSITIVE")
    checks["hash_repro"] = h1 == h2 == r.stability_hash

    art = Path(r.summaries[0].storage_uri)
    checks["manifest"] = (art / "manifest.json").is_file()
    checks["registry"] = bool(
        registry.get_factor_stability_evaluation(r.stability_hash, 1)
    )

    # multi-window
    windows = {x.window for x in r.frames.rolling_ic}
    checks["multi_window"] = {3, 5}.issubset(windows)

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "stability_hash": r.stability_hash,
                "mean_ic_1d": d1.ic_mean,
                "mean_ls_1d": d1.long_short_return,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
