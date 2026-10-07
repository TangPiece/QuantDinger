"""单 tmp 环境：Model Lifecycle E2E（止于 ACTIVE + Repro + lineage）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.model_evaluation import (
    ModelEvaluationRequest,
    ModelEvaluationService,
)
from app.services.research_data.model_evaluation.protocol import ModelEvaluationInject
from app.services.research_data.model_reproducibility import (
    ReproducibilityInject,
    ReproducibilityService,
)
from model_platform_golden.golden import (
    create_formal_version,
    golden_model_spec,
    make_model_platform_env,
)
from phase9f_hardening.lineage_checks import (
    assert_forward_chain,
    assert_reverse_from_version,
)


def _panel():
    rows = []
    for d in range(5):
        for i in range(8):
            label = float(i) + d * 0.01
            rows.append(
                {
                    "date": f"2024-05-{d+1:02d}",
                    "instrument": f"CNStock:{i:06d}",
                    "prediction": label * 0.2 + i,
                    "label": label,
                }
            )
    return rows


def run_model_lifecycle_e2e_chain(tmp: Path) -> dict[str, Any]:
    plat = make_model_platform_env(tmp / "plat")
    repro = ReproducibilityService(tmp / "repro", model_platform=plat)
    plat.bind_reproducibility_service(repro)
    eval_svc = ModelEvaluationService(tmp / "eval", model_platform=plat)
    plat.bind_evaluation_service(eval_svc)

    model = plat.register_model(golden_model_spec(model_code="e2e_9f9"))
    v1 = create_formal_version(plat, model_id=model.model_id, version="1.0.0")
    assert v1.lifecycle == "TRAINED"
    assert v1.training_run_id and v1.artifact_id
    art = plat.get_artifact(v1.artifact_id)
    assert art.status == "AVAILABLE"

    man = repro.get_manifest_for_training_run(v1.training_run_id)
    assert man.repro_manifest_id
    tip = plat.get_repro_manifest(v1.model_version_id)
    assert tip.get("repro_manifest_id") == man.repro_manifest_id

    ev = eval_svc.run_evaluation(
        ModelEvaluationRequest(
            model_version_id=v1.model_version_id,
            evaluation_dataset_hash="e" * 64,
            dataset_hash="d" * 64,
            feature_set_hash="f" * 64,
            label_hash="b" * 64,
            evaluation_start="2024-05-01",
            evaluation_end="2024-05-31",
        ),
        inject=ModelEvaluationInject(predictions=_panel()),
    )
    assert ev.status == "SUCCEEDED"
    assert ev.result is not None and ev.result.overall_status == "PASS"

    v1, appr = plat.approve_version(
        v1.model_version_id, operator="e2e", reason="pass"
    )
    assert appr.decision == "APPROVED"
    assert v1.lifecycle == "APPROVED"

    active = plat.activate(v1.model_version_id, operator="e2e", reason="ship")
    assert active.lifecycle == "ACTIVE"
    # idempotent activate
    again = plat.activate(v1.model_version_id, operator="e2e")
    assert again.model_version_id == active.model_version_id
    assert len(plat.list_activations(model_version_id=v1.model_version_id)) >= 1

    rr = repro.reproduce(
        v1.training_run_id,
        policy_code="REPRO_STRICT_V1",
        inject=ReproducibilityInject(
            skip_execute=True,
            artifact_checksum_original=art.checksum or ("a" * 64),
            artifact_checksum_reproduced=art.checksum or ("a" * 64),
            metrics_original={"loss": 0.1},
            metrics_reproduced={"loss": 0.1},
            predictions_original=[{"prediction": 1.0}],
            predictions_reproduced=[{"prediction": 1.0}],
        ),
    )
    assert rr.result in ("EXACT_MATCH", "NUMERICAL_MATCH")

    tree = plat.get_full_lineage(v1.model_version_id)
    assert_forward_chain(tree)
    assert_reverse_from_version(tree)
    assert tree.get("evaluation_runs")
    assert tree.get("approvals")
    assert tree.get("reproducibility_runs")
    assert tree.get("experiment_refs")

    # switch to v2
    v2 = create_formal_version(plat, model_id=model.model_id, version="2.0.0")
    ev2 = eval_svc.run_evaluation(
        ModelEvaluationRequest(
            model_version_id=v2.model_version_id,
            evaluation_dataset_hash="e" * 64,
            dataset_hash="d" * 64,
            feature_set_hash="f" * 64,
            label_hash="b" * 64,
            evaluation_start="2024-05-01",
            evaluation_end="2024-05-31",
        ),
        inject=ModelEvaluationInject(predictions=_panel()),
    )
    assert ev2.status == "SUCCEEDED"
    v2, appr2 = plat.approve_version(v2.model_version_id, operator="e2e", reason="v2")
    assert appr2.decision == "APPROVED"
    assert v2.lifecycle == "APPROVED"
    plat.activate(v2.model_version_id, operator="e2e", reason="cutover")
    old = plat.get_version(v1.model_version_id)
    new = plat.get_version(v2.model_version_id)
    assert old.lifecycle == "DEPRECATED"
    assert old.deprecate_reason_code == "NEW_VERSION"
    assert new.lifecycle == "ACTIVE"
    actives = [v for v in plat.list_versions(model.model_id) if v.lifecycle == "ACTIVE"]
    assert len(actives) == 1

    # consumer ref only — no Strategy LIVE
    consumer = {
        "model_version_id": new.model_version_id,
        "ref": "research_experiment_stub",
    }
    assert consumer["model_version_id"]
    assert not hasattr(plat, "promote_strategy")

    return {
        "ok": True,
        "model_id": model.model_id,
        "v1": v1.model_version_id,
        "v2": new.model_version_id,
        "repro_result": rr.result,
        "lineage_schema": tree.get("schema"),
    }


__all__ = ["run_model_lifecycle_e2e_chain"]
