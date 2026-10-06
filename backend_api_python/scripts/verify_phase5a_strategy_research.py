#!/usr/bin/env python3
"""Phase 5A 验收：Strategy Research Foundation。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5a_strategy_research.py
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
    from app.services.research_data.strategy_research import (
        compute_strategy_hash,
    )
    from strategy_research_golden.golden import (
        CODE,
        FID,
        PHASH,
        default_spec,
        factor_panel,
        make_env,
        portfolio_positions,
        run_materialize,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase5a_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    factors = factor_panel(20, days=3)
    positions = portfolio_positions(20, days=3)
    spec = default_spec()
    r = run_materialize(svc, factors, positions, spec)

    checks["signal_count"] = len(r.frames.signals) == len(factors)
    checks["pit"] = all(
        s.execution_time > s.knowledge_time for s in r.frames.signals
    )
    checks["positions"] = len(r.frames.positions) == len(positions)
    checks["hash_repro"] = (
        compute_strategy_hash(spec, factor_dataset_hash="dh_5a")
        == r.strategy_hash
    )
    art = Path(r.summary.storage_uri)
    checks["manifest"] = (art / "manifest.json").is_file()
    checks["snapshot"] = (art / "snapshots" / "strategy_spec.json").is_file()
    checks["registry_version"] = bool(
        registry.get_strategy_research(r.strategy_hash)
    )
    checks["registry_code"] = bool(registry.get_research_strategy(CODE))
    checks["factor_immutable"] = (
        registry.get_factor_dataset(FID).factor_ref == "raw_strat@1.0.0"
    )
    checks["portfolio_immutable"] = (
        registry.get_factor_portfolio(PHASH).portfolio_hash == PHASH
    )

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "strategy_hash": r.strategy_hash,
                "signal_rows": len(r.frames.signals),
                "position_rows": len(r.frames.positions),
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
