#!/usr/bin/env python3
"""Phase 9B 验收：Feature / Factor Platform（LocalJson + 9A dataset pin）。"""

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
    from app.services.research_data.feature_factor_platform.protocol import ENGINE_VERSION
    from app.services.research_data.feature_factor_platform.runner import FeatureFactorService
    from feature_factor_platform_golden.golden import (
        GOLDEN_DATASET_REF,
        GOLDEN_FACTOR_REF,
        GOLDEN_FS_REF,
        build_window,
        compute_metadata_inject,
        golden_factor_definition,
        golden_feature_definition,
        golden_feature_set_definition,
        make_feature_factor_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9b_"))
    checks: dict[str, bool] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_feature_factor_platform@1"

    svc, ds, _reg, _q, _c, days = make_feature_factor_env(tmp / "main")
    checks["no_mine_api"] = not hasattr(FeatureFactorService, "mine_factors")
    checks["no_eval_ic_api"] = not hasattr(FeatureFactorService, "evaluate_ic")

    try:
        svc.register_feature(golden_factor_definition())
        checks["taxonomy_rejects_wrong_layer"] = False
    except Exception:
        checks["taxonomy_rejects_wrong_layer"] = True

    feat = svc.register_factor(golden_factor_definition())
    checks["factor_registered"] = bool(feat.factor_hash)

    fs1 = svc.register_feature_set(golden_feature_set_definition())
    fs2_def = golden_feature_set_definition(members=[GOLDEN_FACTOR_REF, "x@1.0.0"])
    fs2_def = fs2_def.model_copy(update={"version": "1.0.1"})
    fs2 = svc.register_feature_set(fs2_def)
    checks["feature_set_hash_stable"] = fs1.feature_set_hash == svc.get_manifest(GOLDEN_FS_REF).feature_set_hash
    checks["member_change_new_hash"] = fs2.feature_set_hash != fs1.feature_set_hash

    window = build_window(days)
    br = svc.build_factor(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        window=window,
        inject=compute_metadata_inject(),
    )
    checks["build_has_factor_hash"] = len(br.factor_hash) == 64
    checks["build_pins_dataset"] = br.dataset_hash == ds.get(GOLDEN_DATASET_REF).dataset_hash
    checks["build_index_exists"] = Path(br.build_index_uri).is_file()

    br_idem = svc.build_factor(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        window=window,
        inject=compute_metadata_inject(),
    )
    checks["build_idempotent"] = br_idem.factor_dataset_id == br.factor_dataset_id

    lin = svc.get_lineage(GOLDEN_FACTOR_REF, dataset_ref=GOLDEN_DATASET_REF)
    checks["lineage_has_dataset"] = any(c.kind == "DATASET" for c in lin.children)
    checks["list_by_dataset"] = GOLDEN_FACTOR_REF in svc.list_by_dataset(br.dataset_hash)

    pkg = ROOT / "app" / "services" / "research_data" / "feature_factor_platform"
    forbidden = ("trading_db", "submit_order", "production_oms")
    clean = True
    for py in pkg.rglob("*.py"):
        if any(tok in py.read_text(encoding="utf-8") for tok in forbidden):
            clean = False
            break
    checks["no_oms_trading_db"] = clean

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
