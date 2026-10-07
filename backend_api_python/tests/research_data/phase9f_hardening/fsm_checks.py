"""Model Platform FSM illegal-transition checks。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.model_platform.lifecycle import (
    ModelLifecycleError,
    assert_transition,
)
from app.services.research_data.model_platform.protocol import ModelPlatformInject
from app.services.research_data.model_platform.runner import ModelPlatformError
from model_platform_golden.golden import (
    create_formal_version,
    golden_model_spec,
    make_model_platform_env,
)


def check_illegal_lifecycle_transitions() -> None:
    with pytest.raises(ModelLifecycleError):
        assert_transition("ACTIVE", "TRAINING")
    with pytest.raises(ModelLifecycleError):
        assert_transition("ACTIVE", "DRAFT")
    with pytest.raises(ModelLifecycleError):
        assert_transition("RETIRED", "ACTIVE")
    with pytest.raises(ModelLifecycleError):
        assert_transition("TRAINED", "ACTIVE")


def check_bare_approved_and_activate_gates(tmp: Path) -> None:
    svc = make_model_platform_env(tmp / "fsm")
    model = svc.register_model(golden_model_spec(model_code="fsm_gate"))
    ver = create_formal_version(svc, model_id=model.model_id)
    svc.transition(ver.model_version_id, "EVALUATING")
    svc.transition(ver.model_version_id, "VALIDATED")
    with pytest.raises(ModelPlatformError, match="approve_version"):
        svc.transition(ver.model_version_id, "APPROVED")
    with pytest.raises(ModelLifecycleError):
        svc.activate(ver.model_version_id)
    # skip gate → APPROVED then ACTIVE ok
    ver, _ = svc.approve_version(
        ver.model_version_id,
        operator="fsm",
        inject=ModelPlatformInject(skip_approval_gate=True),
    )
    assert ver.lifecycle == "APPROVED"
    active = svc.activate(ver.model_version_id, operator="fsm")
    assert active.lifecycle == "ACTIVE"
    with pytest.raises(ModelLifecycleError):
        svc.transition(active.model_version_id, "TRAINING")


def check_no_strategy_live_apis() -> None:
    from app.services.research_data.model_platform.runner import ModelPlatformService
    from app.services.research_data.model_evaluation import ModelEvaluationService
    from app.services.research_data.model_reproducibility import ReproducibilityService

    for cls in (ModelPlatformService, ModelEvaluationService, ReproducibilityService):
        assert not hasattr(cls, "auto_live")
        assert not hasattr(cls, "promote_strategy")
        assert not hasattr(cls, "promote_to_live")


def run_fsm_checks(tmp: Path) -> dict[str, bool]:
    check_illegal_lifecycle_transitions()
    check_bare_approved_and_activate_gates(tmp)
    check_no_strategy_live_apis()
    return {
        "illegal_lifecycle": True,
        "bare_approved_blocked": True,
        "activate_requires_approved": True,
        "no_strategy_live_apis": True,
    }


__all__ = ["run_fsm_checks"]
