#!/usr/bin/env python3
"""Phase 5E CLI：双引擎交叉验证入口（对应 qd research validate）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/qd_research_validate.py \\
        --strategy-hash strat_xxx --start 2020-01-02 --end 2020-01-10

Golden / 无 Registry 策略时可用注入路径（测试）::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/qd_research_validate.py --golden
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="QuantDinger research cross-validation (Phase 5E)"
    )
    parser.add_argument("--strategy-hash", default="", help="5A strategy_hash")
    parser.add_argument("--start", default="", help="YYYY-MM-DD")
    parser.add_argument("--end", default="", help="YYYY-MM-DD")
    parser.add_argument(
        "--realism", default="GROSS", choices=["GROSS", "NET"], help="Baseline GROSS"
    )
    parser.add_argument("--backtest-hash", default="", help="可选：已有 5B hash")
    parser.add_argument("--qlib-run-hash", default="", help="可选：已有 5D hash")
    parser.add_argument(
        "--golden",
        action="store_true",
        help="跑内置 golden（不依赖已有 strategy registry）",
    )
    parser.add_argument(
        "--force", action="store_true", help="强制重算（忽略 CV cache）"
    )
    args = parser.parse_args(argv)

    if args.golden:
        sys.path.insert(0, str(ROOT / "tests" / "research_data"))
        from cross_validation_golden.golden import make_env, run_cv

        tmp = Path(tempfile.mkdtemp(prefix="qd_validate_"))
        os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
        _, _, svc = make_env(tmp)
        result = run_cv(svc, realism=args.realism)
    else:
        if not args.strategy_hash or not args.start or not args.end:
            parser.error(
                "--strategy-hash --start --end required (or use --golden)"
            )
        from app.services.research_data.canonical_store import LocalCanonicalStore
        from app.services.research_data.cross_validation import (
            CrossValidationService,
            CrossValidationSpec,
        )
        from app.services.research_data.registry import LocalJsonRegistry
        from app.services.research_data.research_backtest.protocol import (
            ResearchExecutionPolicy,
        )

        store = LocalCanonicalStore()
        registry = LocalJsonRegistry()
        svc = CrossValidationService(store, registry)
        spec = CrossValidationSpec(
            strategy_hash=args.strategy_hash,
            start_date=date.fromisoformat(args.start),
            end_date=date.fromisoformat(args.end),
            backtest_hash=args.backtest_hash,
            qlib_run_hash=args.qlib_run_hash,
            execution_policy=ResearchExecutionPolicy(mode="NEXT_OPEN"),
            realism=args.realism,  # type: ignore[arg-type]
        )
        meta = {"force_recompute": bool(args.force)}
        if args.backtest_hash and args.qlib_run_hash:
            meta["skip_engine_run"] = True
        result = svc.run(args.strategy_hash, spec, metadata=meta)

    payload = {
        "ok": result.report.status in ("PASSED", "PASSED_WITH_EXPECTED_DIFF"),
        "cv_hash": result.cv_hash,
        "status": result.report.status,
        "storage_uri": result.summary.storage_uri,
        "layers": {L.layer: L.status for L in result.layers or result.report.layers},
        "attribution": result.report.attribution.model_dump(mode="json"),
        "side_by_side": result.report.side_by_side,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
