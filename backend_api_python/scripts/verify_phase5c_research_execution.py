#!/usr/bin/env python3
"""Phase 5C 验收：Cost & Execution Model。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5c_research_execution.py
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
    from research_execution_golden.golden import (
        INST_A,
        make_env,
        make_spec,
        price_bars,
        run_bt,
        trading_days,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase5c_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    days = trading_days(4)
    bars = price_bars(days)
    targets = {
        days[0].isoformat(): [{"instrument_key": INST_A, "target_weight": 1.0}],
        days[2].isoformat(): [],
    }
    rule = {"lot_size": 1, "t_plus": 0, "limit_up_down": False}

    r_gross = run_bt(
        svc, realism="GROSS", days=days, targets=targets, bars=bars, rule_override=rule
    )
    r_net = run_bt(
        svc,
        realism="NET",
        days=days,
        targets=targets,
        bars=bars,
        cost_override={
            "commission_rate": 0.001,
            "stamp_tax_rate": 0.001,
            "slippage_bps": 5.0,
            "minimum_commission": 0.0,
            "transfer_fee_rate": 0.0,
        },
        rule_override=rule,
    )

    checks["gross_ge_net"] = r_gross.frames.nav[-1].nav >= r_net.frames.nav[-1].nav - 1e-6
    checks["has_costs"] = bool(r_net.frames.costs)
    checks["has_fills"] = bool(r_net.frames.fills)
    attr = r_net.frames.attribution or {}
    checks["has_attribution"] = attr.get("delta_return") is not None
    if checks["has_attribution"]:
        bd = attr["breakdown"]
        explained = sum(
            float(bd.get(k) or 0)
            for k in (
                "commission_drag",
                "stamp_tax_drag",
                "slippage_drag",
                "transfer_fee_drag",
                "unfilled_drag",
                "other",
            )
        )
        checks["attribution_closed"] = abs(float(attr["delta_return"]) - explained) < 1e-5
    else:
        checks["attribution_closed"] = False
    checks["registry"] = bool(registry.get_research_backtest(r_net.backtest_hash))
    checks["realism_net"] = r_net.summary.realism == "NET"
    art = Path(r_net.summary.storage_uri)
    checks["manifest"] = (art / "manifest.json").is_file()
    s1 = make_spec(realism="NET", days=days, cost_override={"commission_rate": 0.001})
    s2 = make_spec(realism="NET", days=days, cost_override={"commission_rate": 0.002})
    checks["hash_differs"] = compute_backtest_hash(s1) != compute_backtest_hash(s2)
    checks["gross_ok"] = r_gross.summary.realism == "GROSS"

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "gross_nav": r_gross.frames.nav[-1].nav,
                "net_nav": r_net.frames.nav[-1].nav,
                "attribution": attr,
                "backtest_hash": r_net.backtest_hash,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
