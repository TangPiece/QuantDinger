#!/usr/bin/env python3
"""Phase 9F-8 验收：Reproducible Training。"""

from __future__ import annotations

import hashlib
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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    from app.services.research_data.model_platform.runner import ModelPlatformService
    from app.services.research_data.model_reproducibility import (
        ENGINE_VERSION,
        ReproducibilityInject,
        ReproducibilityService,
    )
    from model_platform_golden.golden import (
        create_formal_version,
        golden_model_spec,
        make_model_platform_env,
    )

    checks: dict[str, bool] = {}
    checks["engine_version"] = ENGINE_VERSION == "qd_model_reproducibility@1"
    checks["no_auto_live"] = not hasattr(ReproducibilityService, "auto_live")
    checks["no_promote_strategy"] = not hasattr(
        ReproducibilityService, "promote_strategy"
    )
    checks["platform_no_promote"] = not hasattr(
        ModelPlatformService, "promote_strategy"
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9f8_"))
    plat = make_model_platform_env(tmp / "plat")
    repro = ReproducibilityService(tmp / "repro", model_platform=plat)
    plat.bind_reproducibility_service(repro)

    model = plat.register_model(golden_model_spec(model_code="verify_repro"))
    ver = create_formal_version(plat, model_id=model.model_id, version="1.0.0")
    run = plat.get_training_run(ver.training_run_id)
    man = repro.get_manifest_for_training_run(run.training_run_id)
    tip = plat.get_repro_manifest(ver.model_version_id)
    checks["captured"] = bool(man.repro_manifest_id)
    checks["tip_pointer"] = tip.get("repro_manifest_id") == man.repro_manifest_id

    run_path = plat._store.training_run_path(training_run_id=run.training_run_id)
    ver_path = plat._store.version_path(model_version_id=ver.model_version_id)
    before_run, before_ver = _sha(run_path), _sha(ver_path)

    ok = repro.reproduce(
        run.training_run_id,
        policy_code="REPRO_STRICT_V1",
        inject=ReproducibilityInject(
            skip_execute=True,
            artifact_checksum_original="a" * 64,
            artifact_checksum_reproduced="a" * 64,
            metrics_original={"loss": 0.1},
            metrics_reproduced={"loss": 0.1},
            predictions_original=[{"prediction": 1.0}],
            predictions_reproduced=[{"prediction": 1.0}],
        ),
    )
    checks["exact_match"] = ok.result == "EXACT_MATCH"

    data = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True, mutate_partition_checksum="f" * 64
        ),
    )
    checks["data_mismatch"] = data.result == "DATA_MISMATCH"

    snap = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True, mutate_snapshot_id="snap_x"
        ),
    )
    checks["input_mismatch"] = snap.result == "INPUT_MISMATCH"

    code = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True, mutate_code_commit="git:other"
        ),
    )
    checks["code_mismatch"] = code.result == "CODE_MISMATCH"

    dep = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True, mutate_dependency_lock_hash="e" * 64
        ),
    )
    checks["dependency_mismatch"] = dep.result == "DEPENDENCY_MISMATCH"

    seed = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(skip_execute=True, mutate_seed=12345),
    )
    checks["seed_mismatch"] = seed.result == "SEED_MISMATCH"

    nd = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True,
            force_non_deterministic=True,
            artifact_checksum_original="a" * 64,
            artifact_checksum_reproduced="b" * 64,
            metrics_original={"loss": 0.1},
            metrics_reproduced={"loss": 0.1},
            predictions_original=[{"prediction": 1.0}],
            predictions_reproduced=[{"prediction": 1.0}],
        ),
    )
    checks["non_deterministic"] = nd.result == "NON_DETERMINISTIC"

    checks["source_run_immutable"] = _sha(run_path) == before_run
    checks["source_version_immutable"] = _sha(ver_path) == before_ver

    art = repro.get_artifact_dir(ok.reproducibility_run_id)
    checks["report_artifact"] = (art / "reproducibility_report.json").is_file()

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
