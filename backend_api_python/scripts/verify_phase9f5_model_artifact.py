#!/usr/bin/env python3
"""Phase 9F-5 验收：Model Artifact Bundle Store / Loader / immutability。"""

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
    from app.services.research_data.model_platform.artifact_manifest import MANIFEST_SCHEMA
    from app.services.research_data.model_platform.protocol import ENGINE_VERSION
    from app.services.research_data.model_platform.runner import (
        ModelPlatformError,
        ModelPlatformService,
    )
    from model_platform_golden.golden import (
        create_formal_version,
        formal_inject,
        golden_job_spec,
        golden_model_spec,
        make_model_platform_env,
    )

    checks: dict[str, bool] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_model_platform@1"
    checks["has_put"] = hasattr(ModelPlatformService, "put_model_artifact")
    checks["has_verify"] = hasattr(ModelPlatformService, "verify_artifact")
    checks["has_load"] = hasattr(ModelPlatformService, "load_model_artifact")
    checks["has_delete"] = hasattr(ModelPlatformService, "delete_artifact")

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9f5_"))
    svc = make_model_platform_env(tmp / "main")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(
            model_id=model.model_id, force_new=True, idempotency_key="v9f5"
        )
    )
    run = svc.execute_training_run(job.run_ids[0], inject=formal_inject())
    checks["execute_ok"] = run.status == "SUCCEEDED" and bool(run.model_version_id)
    ver = svc.get_version(run.model_version_id)
    art = svc.get_artifact(ver.artifact_id)
    checks["available"] = art.status == "AVAILABLE"
    checks["producer"] = art.producer_type == "training_run" and bool(art.producer_id)
    bundle = Path(art.artifact_uri).parent
    checks["bundle_files"] = all(
        (bundle / name).is_file()
        for name in ("model.bin", "manifest.json", "checksum.sha256", "metadata.json")
    )
    man_text = (bundle / "manifest.json").read_text(encoding="utf-8")
    checks["manifest_schema"] = MANIFEST_SCHEMA.split("@")[0] in man_text
    checks["verify_ok"] = svc.verify_artifact(art.artifact_id) is True

    loaded = svc.load_model_artifact(ver.model_version_id)
    checks["load_ok"] = Path(loaded.bin_path).is_file()
    loaded2 = svc.load_model_artifact(ver.model_version_id)
    checks["cache_hit"] = loaded2.from_cache is True

    # tamper
    Path(art.artifact_uri).write_bytes(b"CORRUPT")
    tamper_ok = False
    try:
        svc.verify_artifact(art.artifact_id)
    except ModelPlatformError:
        tamper_ok = True
    checks["tamper_reject"] = tamper_ok and svc.get_artifact(art.artifact_id).status == "CORRUPTED"

    # delete protection on a fresh bound version
    svc2 = make_model_platform_env(tmp / "del")
    m2 = svc2.register_model(golden_model_spec())
    v2 = create_formal_version(svc2, model_id=m2.model_id)
    del_ok = False
    try:
        svc2.delete_artifact(v2.artifact_id)
    except ModelPlatformError:
        del_ok = True
    checks["delete_protected"] = del_ok

    # distinct artifacts
    svc3 = make_model_platform_env(tmp / "two")
    m3 = svc3.register_model(golden_model_spec())
    a = create_formal_version(svc3, model_id=m3.model_id, version="1.0.0")
    b = create_formal_version(
        svc3, model_id=m3.model_id, version="2.0.0", training_run_id="t2"
    )
    checks["distinct_ids"] = a.artifact_id != b.artifact_id
    checks["v1_still_loadable"] = Path(
        svc3.load_model_artifact(a.model_version_id).bin_path
    ).is_file()

    pkg = ROOT / "app" / "services" / "research_data" / "model_platform"
    clean = True
    for py in pkg.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "from app.services.research_data.model_training" in text:
            clean = False
        if "import qlib" in text or "from qlib" in text:
            clean = False
    checks["no_qlib_import"] = clean

    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
