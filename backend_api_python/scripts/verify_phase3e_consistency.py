#!/usr/bin/env python3
"""Phase 3E 验收：Dual Engine Consistency（Golden + 分层归因）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase3e_consistency.py

缺 pyqlib 时双引擎 L0 标记 skipped_qlib（退出码仍 0，若 Production 阶梯通过）。
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

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")

TESTS_RD = ROOT / "tests" / "research_data"
if str(TESTS_RD) not in sys.path:
    sys.path.insert(0, str(TESTS_RD))


def main() -> int:
    from app.services.research_data.backtest.fingerprint import (
        compute_request_fingerprint,
        compute_semantic_fingerprint,
    )
    from app.services.research_data.backtest.presets import research_qlib_relaxed
    from app.services.research_data.backtest.request import BacktestRequest
    from app.services.research_data.backtest_consistency import (
        CONSISTENCY_ENGINE_VERSION,
        KNOWN_DIFF_REASONS,
        ConsistencyArtifactStore,
        ConsistencyEngine,
        policies_for_level,
    )
    from app.services.research_data.backtest_production import (
        ProductionArtifactStore,
        ProductionBacktestEngine,
    )
    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.contracts import ExperimentDefinition
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.registry import LocalJsonRegistry
    from consistency.golden_data import build_bars_by_date, build_targets_by_date

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase3e_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")

    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=tmp / "registry")
    query = DataQuery(store, registry)
    registry.upsert_experiment(
        ExperimentDefinition(
            experiment_id="exp_3e_verify",
            name="phase3e verify",
            dataset_ref="dummy@1",
            snapshot_id="snap_3e_verify",
            dataset_hash="ds_hash_3e_golden",
            strategy_version="golden@1",
            signal_artifact_id="sig_art_3e",
        )
    )
    prod = ProductionBacktestEngine(
        query,
        registry,
        artifact_store=ProductionArtifactStore(root=tmp / "bt_art"),
    )
    eng = ConsistencyEngine(
        registry,
        production_engine=prod,
        qlib_engine=None,
        artifact_store=ConsistencyArtifactStore(root=tmp / "cons_art"),
    )

    # 1) semantic fingerprint
    e1, p1, c1, r1 = research_qlib_relaxed()
    req_q = BacktestRequest(
        experiment_id="exp_3e_verify",
        dataset_hash="ds_hash_3e_golden",
        strategy_version="golden@1",
        start_date="2024-05-06",
        end_date="2024-05-31",
        initial_capital=1_000_000.0,
        engine="qlib",
        execution_policy=e1,
        market_price_policy=p1,
        cost_policy=c1,
        trading_rule=r1,
    )
    req_p = req_q.model_copy(update={"engine": "production"})
    semantic_ok = compute_semantic_fingerprint(req_q) == compute_semantic_fingerprint(
        req_p
    )
    engine_fp_diff = compute_request_fingerprint(req_q) != compute_request_fingerprint(
        req_p
    )

    bars = build_bars_by_date()
    targets = build_targets_by_date()
    exec_p, price_p, cost_p, rules = policies_for_level("L0")
    base = BacktestRequest(
        experiment_id="exp_3e_verify",
        dataset_hash="ds_hash_3e_golden",
        strategy_version="golden@1",
        start_date="2024-05-06",
        end_date="2024-05-31",
        initial_capital=1_000_000.0,
        engine="production",
        execution_policy=exec_p,
        market_price_policy=price_p,
        cost_policy=cost_p,
        trading_rule=rules,
        target_positions_artifact_id="sig_art_3e",
    )

    # 2–3) L0 + L5 reports
    r0 = eng.run(
        base, level="L0", bars_by_date=bars, targets_by_date=targets, run_attribution=False
    )
    r5 = eng.run(
        base, level="L5", bars_by_date=bars, targets_by_date=targets, run_attribution=True
    )

    l0_ok = r0.status in ("PASSED", "SKIPPED_QLIB") and bool(r0.artifact_uris.get("manifest"))
    l5_ok = r5.status != "FAILED"
    no_unknown = all(
        d.reason in KNOWN_DIFF_REASONS
        for d in r5.diffs
        if d.dimension == "rejected"
    )
    has_rejected = any(d.dimension == "rejected" for d in r5.diffs)
    has_attr = len(r5.attribution) > 0

    # 4) optional qlib
    qlib_status = "skipped"
    try:
        import qlib  # noqa: F401

        qlib_status = "available"
    except Exception:
        qlib_status = "missing"

    checks = {
        "semantic_fingerprint": semantic_ok and engine_fp_diff,
        "l0_report": l0_ok,
        "l5_no_failed": l5_ok,
        "l5_no_unknown": no_unknown,
        "l5_rejected_explained": has_rejected and no_unknown,
        "l5_attribution": has_attr,
        "engine_version": r0.engine_version == CONSISTENCY_ENGINE_VERSION,
    }
    all_ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": all_ok,
                "checks": checks,
                "qlib": qlib_status,
                "l0_status": r0.status,
                "l5_status": r5.status,
                "l5_max_equity_diff": r5.max_equity_diff,
                "run_id_l5": r5.run_id,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
