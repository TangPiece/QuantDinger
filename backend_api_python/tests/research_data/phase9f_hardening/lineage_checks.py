"""正向 / 反向 lineage 检查。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.model_platform.protocol import ModelPlatformInject
from app.services.research_data.model_reproducibility import ReproducibilityService
from model_platform_golden.golden import (
    create_formal_version,
    golden_model_spec,
    make_model_platform_env,
)


def assert_forward_chain(tree: dict[str, Any]) -> None:
    mv = tree.get("model_version") or {}
    assert mv.get("model_version_id")
    assert mv.get("training_run_id")
    assert mv.get("artifact_id")
    assert mv.get("dataset_hash")
    assert mv.get("feature_set_hash")
    assert mv.get("label_hash")
    assert mv.get("processor_version")
    assert tree.get("training_run") is not None
    assert tree.get("artifact") is not None
    assert tree.get("boundaries", {}).get("model_active_ne_strategy_live") is True


def assert_reverse_from_version(tree: dict[str, Any]) -> None:
    mv = tree["model_version"]
    tr = tree["training_run"]
    assert tr["dataset_hash"] == mv["dataset_hash"]
    assert tr["feature_set_hash"] == mv["feature_set_hash"]
    assert tr["label_hash"] == mv["label_hash"]
    man = tree.get("reproducibility_manifest")
    if man:
        assert man.get("dataset_hash") == mv["dataset_hash"]
        assert man.get("seeds") is not None
        assert man.get("environment_hash")


def run_lineage_checks(tmp: Path) -> dict[str, bool]:
    plat = make_model_platform_env(tmp / "lin")
    repro = ReproducibilityService(tmp / "repro", model_platform=plat)
    plat.bind_reproducibility_service(repro)
    model = plat.register_model(golden_model_spec(model_code="lin_9f9"))
    ver = create_formal_version(plat, model_id=model.model_id)
    ver, _ = plat.approve_version(
        ver.model_version_id,
        operator="lin",
        inject=ModelPlatformInject(skip_approval_gate=True),
    )
    plat.activate(ver.model_version_id, operator="lin")
    tree = plat.get_full_lineage(ver.model_version_id)
    assert_forward_chain(tree)
    assert_reverse_from_version(tree)
    assert tree.get("model", {}).get("model_id") == model.model_id
    assert any(
        a.get("to_model_version_id") == ver.model_version_id
        for a in (tree.get("activation_records") or [])
    )
    assert tree.get("experiment_refs")
    return {
        "forward_complete": True,
        "reverse_complete": True,
        "full_lineage_api": True,
        "activation_in_tree": True,
    }


__all__ = [
    "assert_forward_chain",
    "assert_reverse_from_version",
    "run_lineage_checks",
]
