#!/usr/bin/env python3
"""Phase 9A 验收：Research Dataset Platform（LocalJson + 本地 artifacts）。"""

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
    from app.services.research_data.dataset_platform.protocol import ENGINE_VERSION
    from app.services.research_data.dataset_platform.runner import DatasetPlatformError
    from dataset_platform_golden.golden import (
        GOLDEN_DATASET_REF,
        golden_bad_pit_inject,
        golden_dataset_definition,
        golden_empty_snapshot_inject,
        golden_snapshot_items,
        make_dataset_platform_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9a_"))
    checks: dict[str, bool] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_dataset_platform@1"

    svc, reg, dq, _store = make_dataset_platform_env(tmp / "main")
    definition = golden_dataset_definition()
    handle = svc.build_and_register(definition, snapshot_items=golden_snapshot_items())
    checks["manifest_uri_nonempty"] = bool(handle.manifest_uri)
    checks["dataset_hash_len"] = len(handle.dataset_hash) == 64

    manifest = svc.get_manifest(GOLDEN_DATASET_REF)
    store = svc._store  # noqa: SLF001
    def_path = store.def_path(definition)
    man_path = store.manifest_path(definition)
    checks["def_json_exists"] = def_path.is_file()
    checks["manifest_json_exists"] = man_path.is_file()
    checks["manifest_hash_match"] = manifest.dataset_hash == handle.dataset_hash

    h2 = svc.build_and_register(definition, snapshot_items=golden_snapshot_items())
    checks["idempotent_rebuild"] = h2.dataset_hash == handle.dataset_hash

    mutated = definition.model_copy(update={"features": definition.features + ["extra_col"]})
    try:
        svc.build_and_register(mutated, snapshot_items=golden_snapshot_items())
        checks["overwrite_rejected"] = False
    except DatasetPlatformError:
        checks["overwrite_rejected"] = True

    v2 = definition.model_copy(update={"version": "1.1.0"})
    h_v2 = svc.build_and_register(v2, snapshot_items=golden_snapshot_items())
    checks["bump_version_ok"] = h_v2.dataset_hash != handle.dataset_hash and bool(h_v2.manifest_uri)

    feat_def = golden_dataset_definition(features=["close"])
    feat_def = feat_def.model_copy(update={"version": "1.2.0"})
    h_feat = svc.build_and_register(feat_def, snapshot_items=golden_snapshot_items())
    checks["feature_change_new_hash"] = h_feat.dataset_hash != handle.dataset_hash

    try:
        svc.build_and_register(
            definition,
            snapshot_items=golden_snapshot_items(),
            inject=golden_bad_pit_inject(),
        )
        checks["gate_rejects_pit"] = False
    except DatasetPlatformError:
        checks["gate_rejects_pit"] = True

    try:
        svc.build_and_register(
            definition,
            snapshot_items=golden_snapshot_items(),
            inject=golden_empty_snapshot_inject(),
        )
        checks["gate_rejects_empty_snapshot"] = False
    except DatasetPlatformError:
        checks["gate_rejects_empty_snapshot"] = True

    dq_h = dq.dataset(GOLDEN_DATASET_REF)
    checks["dataquery_dataset"] = dq_h.dataset_hash == handle.dataset_hash and bool(
        dq_h.manifest_uri
    )

    pkg = ROOT / "app" / "services" / "research_data" / "dataset_platform"
    forbidden = ("trading_db", "submit_order", "production_oms")
    clean = True
    for py in pkg.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if any(tok in text for tok in forbidden):
            clean = False
            break
    checks["no_oms_trading_db"] = clean

    reg_h = reg.get_dataset(GOLDEN_DATASET_REF)
    checks["registry_manifest_uri"] = bool(reg_h.manifest_uri)

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
