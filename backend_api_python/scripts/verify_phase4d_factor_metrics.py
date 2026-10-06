#!/usr/bin/env python3
"""Phase 4D 验收：IC / RankIC / ICIR。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4d_factor_metrics.py
"""

from __future__ import annotations

import json
import math
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
    from app.services.research_data.factor_lab.metrics import compute_metric_hash
    from app.services.research_data.factor_lab.metrics.calculators import (
        CrossSectionalICEngine,
        PearsonICCalculator,
    )
    from factor_lab_metrics.golden import (
        D1,
        D2,
        EVAL_HASH,
        constant_factor_panel,
        default_spec,
        make_env,
        perfect_rank_panel,
        tiny_panel,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4d_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    def run(records, spec=None):
        return svc.run(
            EVAL_HASH,
            spec or default_spec(),
            metadata={"evaluation_records": records, "force_recompute": True},
        )

    r = run(perfect_rank_panel())
    pts = {(p.evaluation_date, p.horizon): p for p in r.timeseries.points}
    checks["pearson_spearman"] = (
        abs(pts[(D1, 1)].rank_ic - 1.0) < 1e-9
        and abs(pts[(D2, 1)].rank_ic - (-1.0)) < 1e-9
        and pts[(D1, 1)].ic > 0
        and pts[(D2, 1)].ic < 0
    )

    s1 = next(x for x in r.summaries if x.horizon == 1)
    checks["icir_tstat_ratio"] = (
        s1.valid_day_count == 2
        and s1.std_ic is not None
        and s1.ic_ir is not None
        and s1.ic_t_stat is not None
        and abs(s1.positive_ic_ratio - 0.5) < 1e-9
    )

    # 按日 vs 池化
    daily = [p.ic for p in r.timeseries.points if p.horizon == 1 and p.valid]
    mean_daily = sum(daily) / len(daily)
    panel = perfect_rank_panel()
    pooled = PearsonICCalculator().day_corr(
        [x["factor_value"] for x in panel],
        [x["forward_return_1d"] for x in panel],
    )
    checks["cross_section_grouping"] = abs(mean_daily - (pooled or 0)) > 1e-6 or abs(
        mean_daily
    ) < abs(pooled or 99)

    checks["multi_horizon"] = {s.horizon for s in r.summaries} == {1, 5}

    r_tiny = run(tiny_panel(), default_spec(horizons=[1], min_cross_section_size=30))
    checks["min_sample"] = all(not p.valid for p in r_tiny.timeseries.points)

    series_c = CrossSectionalICEngine().calculate(
        constant_factor_panel(),
        default_spec(horizons=[1], min_cross_section_size=3),
        metric_hash="c",
    )
    checks["constant_factor"] = (
        series_c.points[0].ic is None and not series_c.points[0].valid
    )

    checks["direction_preserve"] = pts[(D2, 1)].ic < 0 and not math.isnan(
        pts[(D2, 1)].ic
    )

    spec = default_spec()
    h = compute_metric_hash(spec)
    a = run(perfect_rank_panel(), spec)
    b = run(perfect_rank_panel(), spec)
    checks["hash_repro"] = (
        a.metric_hash == b.metric_hash == h
        and a.summaries[0].mean_ic == b.summaries[0].mean_ic
    )

    uri = Path(a.summaries[0].storage_uri or "")
    checks["manifest"] = (uri / "manifest.json").is_file() and (
        uri / "summary.json"
    ).is_file()
    checks["registry"] = (
        registry.get_factor_evaluation_summary(h, 1).metric_hash == h
    )

    all_ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": all_ok,
                "checks": checks,
                "metric_hash": h,
                "mean_ic_1d": s1.mean_ic,
                "mean_rank_ic_1d": s1.mean_rank_ic,
                "ic_ir_1d": s1.ic_ir,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
