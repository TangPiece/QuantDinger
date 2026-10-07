"""Phase 9F-7：Model Lifecycle & Approval。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.model_evaluation import (
    ModelEvaluationRequest,
    ModelEvaluationService,
)
from app.services.research_data.model_evaluation.protocol import ModelEvaluationInject
from app.services.research_data.model_platform.lifecycle import ModelLifecycleError
from app.services.research_data.model_platform.protocol import (
    ENGINE_VERSION,
    ModelPlatformInject,
)
from app.services.research_data.model_platform.runner import (
    ModelPlatformError,
    ModelPlatformService,
)
from model_platform_golden.golden import (
    create_formal_version,
    golden_model_spec,
    make_model_platform_env,
)


def _panel(*, n_dates: int = 5, n_inst: int = 8, seed: float = 0.05):
    rows = []
    for d in range(n_dates):
        date = f"2024-01-{d+1:02d}"
        for i in range(n_inst):
            label = float(i) + d * 0.01
            pred = label * seed + i * 0.1
            rows.append(
                {
                    "date": date,
                    "instrument": f"CNStock:{i:06d}",
                    "prediction": pred,
                    "label": label,
                }
            )
    return rows


def _eval_pass(plat: ModelPlatformService, ver_id: str, root: Path):
    eval_svc = ModelEvaluationService(root, model_platform=plat)
    plat.bind_evaluation_service(eval_svc)
    run = eval_svc.run_evaluation(
        ModelEvaluationRequest(
            model_version_id=ver_id,
            evaluation_dataset_hash="e" * 64,
            dataset_hash="d" * 64,
            feature_set_hash="f" * 64,
            label_hash="b" * 64,
            snapshot_id="snap_eval",
            evaluation_start="2024-01-01",
            evaluation_end="2024-01-31",
        ),
        inject=ModelEvaluationInject(
            predictions=_panel(),
            known_hashes={
                "evaluation_dataset_hash": "e" * 64,
                "feature_set_hash": "f" * 64,
                "label_hash": "b" * 64,
                "snapshot_id": "snap_eval",
            },
        ),
    )
    assert run.status == "SUCCEEDED"
    assert run.result is not None
    assert run.result.overall_status == "PASS"
    return eval_svc, run


def test_engine_version_unchanged():
    assert ENGINE_VERSION == "qd_model_platform@1"


def test_no_auto_live_or_promote_strategy():
    assert not hasattr(ModelPlatformService, "auto_live")
    assert not hasattr(ModelPlatformService, "promote_strategy")


def test_bare_approved_transition_forbidden(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "bare")
    model = plat.register_model(golden_model_spec())
    ver = create_formal_version(plat, model_id=model.model_id)
    plat.transition(ver.model_version_id, "EVALUATING")
    plat.transition(ver.model_version_id, "VALIDATED")
    with pytest.raises(ModelPlatformError, match="approve_version"):
        plat.transition(ver.model_version_id, "APPROVED")


def test_approve_pass_path(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "ok")
    model = plat.register_model(golden_model_spec())
    ver = create_formal_version(plat, model_id=model.model_id)
    _eval_pass(plat, ver.model_version_id, tmp_path / "eval")
    updated, approval = plat.approve_version(
        ver.model_version_id, operator="alice", reason="metrics ok"
    )
    assert approval.decision == "APPROVED"
    assert approval.immutable is True
    assert updated.lifecycle == "APPROVED"
    assert plat.list_approvals(model_version_id=ver.model_version_id)


def test_approve_rejects_without_eval(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "noeval")
    model = plat.register_model(golden_model_spec())
    ver = create_formal_version(plat, model_id=model.model_id)
    plat.transition(ver.model_version_id, "EVALUATING")
    plat.transition(ver.model_version_id, "VALIDATED")
    updated, approval = plat.approve_version(
        ver.model_version_id, operator="bob", reason="try"
    )
    assert approval.decision == "REJECTED"
    assert updated.lifecycle == "VALIDATED"
    assert "evaluation_missing" in (approval.gate_dump.get("reasons") or [])


def test_activate_single_active_and_record(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "act")
    model = plat.register_model(golden_model_spec(model_code="alpha_switch"))
    v17 = create_formal_version(plat, model_id=model.model_id, version="1.7.0")
    _eval_pass(plat, v17.model_version_id, tmp_path / "eval17")
    v17, _ = plat.approve_version(v17.model_version_id, operator="ops", reason="v17")
    active17 = plat.activate(v17.model_version_id, operator="ops", reason="ship v17")
    assert active17.lifecycle == "ACTIVE"

    v18 = create_formal_version(plat, model_id=model.model_id, version="1.8.0")
    _eval_pass(plat, v18.model_version_id, tmp_path / "eval18")
    v18, _ = plat.approve_version(v18.model_version_id, operator="ops", reason="v18")
    active18 = plat.activate(v18.model_version_id, operator="ops", reason="ship v18")
    assert active18.lifecycle == "ACTIVE"

    old = plat.get_version(v17.model_version_id)
    assert old.lifecycle == "DEPRECATED"
    assert old.deprecate_reason_code == "NEW_VERSION"

    actives = [v for v in plat.list_versions(model.model_id) if v.lifecycle == "ACTIVE"]
    assert len(actives) == 1
    assert actives[0].model_version_id == v18.model_version_id

    records = plat.list_activations(model_id=model.model_id)
    assert len(records) >= 2
    last = records[-1]
    assert last.from_model_version_id == v17.model_version_id
    assert last.to_model_version_id == v18.model_version_id


def test_revoke_appends_revoked_and_deprecates(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "rev")
    model = plat.register_model(golden_model_spec(model_code="alpha_rev"))
    ver = create_formal_version(plat, model_id=model.model_id)
    _eval_pass(plat, ver.model_version_id, tmp_path / "eval_rev")
    ver, appr = plat.approve_version(ver.model_version_id, operator="carol", reason="ok")
    assert appr.decision == "APPROVED"
    approved_id = appr.approval_id

    deprecated, rev = plat.revoke_approval(
        ver.model_version_id, reason="rethink", operator="carol"
    )
    assert rev.decision == "REVOKED"
    assert rev.approval_id != approved_id
    assert deprecated.lifecycle == "DEPRECATED"

    # 旧 APPROVED 行未改写
    still = plat.list_approvals(model_version_id=ver.model_version_id)
    kept = next(a for a in still if a.approval_id == approved_id)
    assert kept.decision == "APPROVED"


def test_activate_requires_approved(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "need")
    model = plat.register_model(golden_model_spec(model_code="alpha_need"))
    ver = create_formal_version(plat, model_id=model.model_id)
    with pytest.raises(ModelLifecycleError):
        plat.activate(ver.model_version_id)


def test_skip_approval_gate_inject_only(tmp_path: Path):
    plat = make_model_platform_env(tmp_path / "skip")
    model = plat.register_model(golden_model_spec(model_code="alpha_skip"))
    ver = create_formal_version(plat, model_id=model.model_id)
    plat.transition(ver.model_version_id, "EVALUATING")
    plat.transition(ver.model_version_id, "VALIDATED")
    updated, approval = plat.approve_version(
        ver.model_version_id,
        operator="test",
        inject=ModelPlatformInject(skip_approval_gate=True),
    )
    assert approval.decision == "APPROVED"
    assert updated.lifecycle == "APPROVED"
