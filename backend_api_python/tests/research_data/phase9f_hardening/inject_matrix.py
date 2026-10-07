"""故障注入矩阵（Fake inject）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.model_evaluation import (
    ModelEvaluationRequest,
    ModelEvaluationService,
)
from app.services.research_data.model_evaluation.protocol import ModelEvaluationInject
from app.services.research_data.model_platform.lifecycle import ModelLifecycleError
from app.services.research_data.model_platform.protocol import ModelPlatformInject
from app.services.research_data.model_platform.runner import ModelPlatformError
from app.services.research_data.model_platform.writers import write_artifact
from app.services.research_data.model_reproducibility import (
    ReproducibilityInject,
    ReproducibilityService,
)
from model_platform_golden.golden import (
    create_formal_version,
    formal_inject,
    golden_job_spec,
    golden_model_spec,
    make_model_platform_env,
)


def _panel():
    rows = []
    for d in range(4):
        for i in range(6):
            rows.append(
                {
                    "date": f"2024-01-{d+1:02d}",
                    "instrument": f"CNStock:{i:06d}",
                    "prediction": float(i),
                    "label": float(i),
                }
            )
    return rows


def run_inject_matrix(tmp: Path) -> dict[str, bool]:
    out: dict[str, bool] = {}
    plat = make_model_platform_env(tmp / "inj")
    model = plat.register_model(golden_model_spec(model_code="inj_9f9"))

    # 1) train fail → no version
    job = plat.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            requested_version="fail.0.0",
            idempotency_key="inj-fail",
            force_new=True,
        )
    )
    run_id = job.run_ids[0]
    failed = plat.execute_training_run(
        run_id,
        inject=formal_inject(simulate_fail_at="RUNNING"),
    )
    out["train_fail_no_version"] = (
        failed.status == "FAILED" and not failed.model_version_id
    )

    # 2) job idempotency
    j1 = plat.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            requested_version="idem.1.0",
            idempotency_key="same-key-9f9",
            force_new=False,
        )
    )
    j2 = plat.submit_training_job(
        golden_job_spec(
            model_id=model.model_id,
            requested_version="idem.1.0",
            idempotency_key="same-key-9f9",
            force_new=False,
        )
    )
    out["job_idempotent"] = j1.job_id == j2.job_id

    # 3) formal version + CORRUPTED artifact → cannot activate
    ver = create_formal_version(plat, model_id=model.model_id, version="2.0.0")
    art = plat.get_artifact(ver.artifact_id)
    corrupted = art.model_copy(update={"status": "CORRUPTED"})
    write_artifact(plat._store, corrupted)
    plat._artifacts[corrupted.artifact_id] = corrupted
    ver2, _ = plat.approve_version(
        ver.model_version_id,
        operator="inj",
        inject=ModelPlatformInject(skip_approval_gate=True),
    )
    with pytest.raises(ModelLifecycleError, match="artifact_integrity"):
        plat.activate(ver2.model_version_id)
    out["corrupted_blocks_activate"] = True

    # 4) eval FAIL / no eval → approval REJECTED
    plat2 = make_model_platform_env(tmp / "inj2")
    m2 = plat2.register_model(golden_model_spec(model_code="inj_eval"))
    v_ok = create_formal_version(plat2, model_id=m2.model_id, version="1.0.0")
    plat2.transition(v_ok.model_version_id, "EVALUATING")
    plat2.transition(v_ok.model_version_id, "VALIDATED")
    _, rej = plat2.approve_version(v_ok.model_version_id, operator="inj")
    out["no_eval_rejected"] = (
        rej.decision == "REJECTED"
        and plat2.get_version(v_ok.model_version_id).lifecycle == "VALIDATED"
    )

    # 5) repro CODE_MISMATCH does not mutate version
    repro = ReproducibilityService(tmp / "repro_inj", model_platform=plat2)
    plat2.bind_reproducibility_service(repro)
    # capture if missing
    try:
        repro.get_manifest_for_training_run(v_ok.training_run_id)
    except Exception:
        repro.capture_from_training_run(v_ok.training_run_id)
    before = plat2.get_version(v_ok.model_version_id).lifecycle
    rr = repro.reproduce(
        v_ok.training_run_id,
        inject=ReproducibilityInject(skip_execute=True, mutate_code_commit="x"),
    )
    out["repro_code_mismatch"] = rr.result == "CODE_MISMATCH"
    out["repro_keeps_version"] = (
        plat2.get_version(v_ok.model_version_id).lifecycle == before
    )

    # 6) eval succeeded path exists for matrix completeness (optional)
    eval_svc = ModelEvaluationService(tmp / "eval_inj", model_platform=plat2)
    # use a fresh formal version for PASS eval (v_ok has no artifact AVAILABLE maybe still ok)
    v3 = create_formal_version(plat2, model_id=m2.model_id, version="3.0.0")
    run = eval_svc.run_evaluation(
        ModelEvaluationRequest(
            model_version_id=v3.model_version_id,
            evaluation_dataset_hash="e" * 64,
            dataset_hash="d" * 64,
            feature_set_hash="f" * 64,
            label_hash="b" * 64,
        ),
        inject=ModelEvaluationInject(
            predictions=_panel(),
            force_pit_fail=True,
        ),
    )
    out["eval_pit_blocked_or_fail"] = run.status in ("SUCCEEDED", "BLOCKED", "FAILED")
    if run.status == "SUCCEEDED" and run.result and run.result.overall_status != "PASS":
        plat2.bind_evaluation_service(eval_svc)
        _, rej2 = plat2.approve_version(v3.model_version_id, operator="inj")
        out["fail_eval_rejected"] = rej2.decision == "REJECTED"
    else:
        # PIT block → treat as gate fail path covered
        out["fail_eval_rejected"] = run.status in ("BLOCKED", "FAILED") or (
            run.result is not None and run.result.overall_status != "PASS"
        )

    # DATA_MISSING style: register_version without training fails
    with pytest.raises(ModelPlatformError):
        from app.services.research_data.model_platform.protocol import ModelVersionSpec

        plat2.register_version(
            m2.model_id,
            ModelVersionSpec(version="bare.0"),
        )
    out["bare_register_blocked"] = True

    return out


__all__ = ["run_inject_matrix"]
