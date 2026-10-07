#!/usr/bin/env python3
"""Phase 9E 验收：Factor Library Platform。"""

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
    from app.services.research_data.factor_library_platform.protocol import (
        ENGINE_VERSION,
        FactorSearchQuery,
    )
    from app.services.research_data.factor_library_platform.runner import FactorLibraryService
    from factor_library_platform_golden.golden import (
        GOLDEN_FACTOR_REF,
        GOLDEN_FACTOR_REF_B,
        library_inject,
        make_factor_library_env,
        run_golden_evaluation,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9e_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_factor_library_platform@1"
    lib, eval_svc, _ds, _reg, days, window = make_factor_library_env(tmp / "main")

    checks["no_auto_live"] = not hasattr(FactorLibraryService, "auto_live")
    checks["no_optimize_mv"] = not hasattr(FactorLibraryService, "optimize_mv")
    checks["no_promote_strategy"] = not hasattr(FactorLibraryService, "promote_strategy")
    checks["has_promote"] = hasattr(lib, "promote_to_library")
    checks["has_to_feature_set"] = hasattr(lib, "to_feature_set")

    from evaluation_platform_golden.golden import GOLDEN_DATASET_REF, evaluation_inject

    blocked = eval_svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        window=window,
        inject=evaluation_inject(gate_blocked=True),
    )
    gate_fail = False
    try:
        lib.promote_to_library(
            factor_ref=GOLDEN_FACTOR_REF,
            evaluation_id=blocked.evaluation_id,
        )
    except Exception:
        gate_fail = True
    checks["gate_failure_no_approved"] = gate_fail

    run = run_golden_evaluation(eval_svc, window, days)
    entry = lib.promote_to_library(
        factor_ref=GOLDEN_FACTOR_REF,
        evaluation_id=run.evaluation_id,
        tags=["verify"],
        category="MOMENTUM",
    )
    checks["promotion_has_eval"] = bool(entry.evaluation_id and entry.factor_hash)
    active = lib.activate(entry.entry_id)
    checks["active_searchable"] = active.lifecycle == "ACTIVE" and bool(
        lib.search(FactorSearchQuery(lifecycle=["ACTIVE"], tags_any=["verify"]))
    )

    inj = library_inject(
        weight_metrics={
            GOLDEN_FACTOR_REF: {"icir": 0.3, "volatility": 0.15},
            GOLDEN_FACTOR_REF_B: {"icir": 0.1, "volatility": 0.25},
        },
        cluster_corr_matrix={
            GOLDEN_FACTOR_REF: {GOLDEN_FACTOR_REF: 1.0, GOLDEN_FACTOR_REF_B: 0.88},
            GOLDEN_FACTOR_REF_B: {GOLDEN_FACTOR_REF: 0.88, GOLDEN_FACTOR_REF_B: 1.0},
        },
    )
    coll = lib.create_collection([GOLDEN_FACTOR_REF, GOLDEN_FACTOR_REF_B])
    spec_eq = lib.create_portfolio_spec(collection_id=coll.collection_id, weight_method="EQUAL", inject=inj)
    spec_ic = lib.create_portfolio_spec(
        member_refs=[GOLDEN_FACTOR_REF, GOLDEN_FACTOR_REF_B],
        weight_method="ICIR",
        inject=inj,
    )
    checks["collection_ne_portfolio"] = (
        coll.collection_hash != spec_eq.portfolio_spec_hash != spec_ic.portfolio_spec_hash
    )
    w_methods = {}
    for m in ("EQUAL", "ICIR", "RISK", "CORR_ADJUSTED"):
        sp = lib.create_portfolio_spec(
            member_refs=[GOLDEN_FACTOR_REF, GOLDEN_FACTOR_REF_B],
            weight_method=m,  # type: ignore[arg-type]
            inject=inj,
        )
        w = lib.resolve_weights(sp.portfolio_id, inject=inj)
        w_methods[m] = len(w) == 2 and abs(sum(w.values()) - 1.0) < 1e-5
    checks["four_weight_methods"] = all(w_methods.values())

    cluster = lib.build_cluster([GOLDEN_FACTOR_REF, GOLDEN_FACTOR_REF_B], inject=inj)
    checks["cluster_hash"] = bool(cluster.cluster_hash and cluster.member_refs)

    fs = lib.to_feature_set(collection_id=coll.collection_id, code="v9e", version="1.0.0")
    checks["feature_set_members"] = GOLDEN_FACTOR_REF in fs.member_refs

    pkg = ROOT / "app" / "services" / "research_data" / "factor_library_platform"
    forbidden = ("optimize_mv", "auto_live", "mean_variance", "risk_parity")
    clean = True
    for py in pkg.rglob("*.py"):
        low = py.read_text(encoding="utf-8").lower()
        for tok in forbidden:
            if tok in low:
                clean = False
                break
    checks["forbidden_tokens"] = clean

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
