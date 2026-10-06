#!/usr/bin/env python3
"""Phase 5B 验收：Research Backtest Engine。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5b_research_backtest.py
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
    from app.services.research_data.research_backtest import compute_backtest_hash
    from research_backtest_golden.golden import (
        INST_A,
        default_spec,
        long_only_targets,
        make_env,
        price_bars,
        run_backtest,
        trading_days,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase5b_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    days = trading_days(4)
    bars = price_bars(
        days,
        a_open=[10.0, 11.0, 12.0, 13.0],
        a_close=[10.5, 11.5, 12.5, 13.5],
    )
    targets = {
        days[0].isoformat(): [{"instrument_key": INST_A, "target_weight": 1.0}]
    }
    spec = default_spec(mode="NEXT_OPEN", days=days)
    r = run_backtest(svc, spec=spec, targets=targets, bars=bars)

    checks["hash_repro"] = compute_backtest_hash(spec) == r.backtest_hash
    checks["fill_open"] = r.frames.metadata.get("fill_field") == "open"
    by_date = {}
    for p in r.frames.positions:
        by_date.setdefault(p.trading_date, set()).add(p.instrument_key)
    checks["no_hold_signal_day"] = INST_A not in by_date.get(days[0], set())
    checks["hold_exec_day"] = INST_A in by_date.get(days[1], set())
    nav1 = next(n.nav for n in r.frames.nav if n.trading_date == days[1])
    checks["nav_hand_calc"] = abs(nav1 - 11.5 / 11.0) < 1e-9
    art = Path(r.summary.storage_uri)
    checks["manifest"] = (art / "manifest.json").is_file()
    checks["metrics_file"] = (art / "metrics" / "summary.json").is_file()
    checks["registry"] = bool(registry.get_research_backtest(r.backtest_hash))
    checks["has_metrics"] = bool(r.frames.metrics.get("n_days"))

    # SAME_CLOSE look-ahead 显式标记
    r2 = run_backtest(
        svc,
        spec=default_spec(mode="SAME_CLOSE", days=days),
        targets=long_only_targets(days[:1]),
        bars=bars,
    )
    checks["allows_same_close"] = (
        r2.summary.metadata.get("allows_same_close") is True
    )

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "backtest_hash": r.backtest_hash,
                "nav_rows": len(r.frames.nav),
                "metrics": r.frames.metrics,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
