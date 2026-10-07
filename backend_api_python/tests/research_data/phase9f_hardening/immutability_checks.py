"""历史对象不可变 + 禁删。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services.research_data.model_platform.protocol import ModelPlatformInject
from app.services.research_data.model_platform.runner import ModelPlatformError
from app.services.research_data.model_reproducibility import (
    ReproducibilityInject,
    ReproducibilityService,
)
from model_platform_golden.golden import (
    create_formal_version,
    golden_model_spec,
    make_model_platform_env,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_immutability_battery(tmp: Path) -> dict[str, bool]:
    plat = make_model_platform_env(tmp / "plat")
    repro = ReproducibilityService(tmp / "repro", model_platform=plat)
    plat.bind_reproducibility_service(repro)

    model = plat.register_model(golden_model_spec(model_code="immut_9f9"))
    ver = create_formal_version(plat, model_id=model.model_id)
    run = plat.get_training_run(ver.training_run_id)

    run_path = plat._store.training_run_path(training_run_id=run.training_run_id)
    ver_path = plat._store.version_path(model_version_id=ver.model_version_id)
    before_run, before_ver = _sha(run_path), _sha(ver_path)

    content_hash = plat.get_version(ver.model_version_id).version_content_hash
    man = repro.get_manifest_for_training_run(run.training_run_id)
    man_path = repro._store.manifest_path(repro_manifest_id=man.repro_manifest_id)
    before_man = _sha(man_path)

    ver, appr = plat.approve_version(
        ver.model_version_id,
        operator="imm",
        inject=ModelPlatformInject(skip_approval_gate=True),
    )
    appr_path = plat._store.approval_path(approval_id=appr.approval_id)
    before_appr = _sha(appr_path)

    plat.activate(ver.model_version_id, operator="imm")

    repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True,
            mutate_code_commit="git:other",
        ),
    )

    assert _sha(run_path) == before_run
    assert _sha(appr_path) == before_appr
    assert _sha(man_path) == before_man
    assert (
        plat.get_version(ver.model_version_id).version_content_hash == content_hash
    )
    # version file may change lifecycle only; lineage hash frozen
    assert ver_path.is_file()

    with pytest.raises(ModelPlatformError, match="delete_version forbidden"):
        plat.delete_version(ver.model_version_id)

    return {
        "training_run_immutable": True,
        "approval_immutable": True,
        "repro_manifest_immutable": True,
        "version_content_hash_frozen": True,
        "delete_forbidden": True,
    }


__all__ = ["run_immutability_battery"]
