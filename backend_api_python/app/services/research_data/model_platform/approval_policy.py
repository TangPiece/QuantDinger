"""Model Approval Policy presets（9F-7）。"""

from __future__ import annotations

from .protocol import ModelApprovalPolicy

MODEL_APPROVAL_V1 = ModelApprovalPolicy(
    policy_code="MODEL_APPROVAL_V1",
    version="1.0.0",
    name="Model Approval V1",
    allowed_overall_status=["PASS"],
    require_eval_succeeded=True,
    require_artifact_available=True,
    require_lineage_hashes=True,
    require_pit=True,
    min_mean_ic=None,
    min_mean_rank_ic=None,
    min_ic_ir=None,
)

_PRESETS: dict[str, ModelApprovalPolicy] = {
    MODEL_APPROVAL_V1.policy_code: MODEL_APPROVAL_V1,
}


def get_approval_policy(policy_code: str = "MODEL_APPROVAL_V1") -> ModelApprovalPolicy:
    code = (policy_code or "MODEL_APPROVAL_V1").strip() or "MODEL_APPROVAL_V1"
    if code not in _PRESETS:
        raise KeyError(f"unknown approval policy: {code}")
    return _PRESETS[code]


def policy_version_ref(policy: ModelApprovalPolicy | None = None) -> str:
    p = policy or MODEL_APPROVAL_V1
    return f"{p.policy_code}@{p.version}"


__all__ = [
    "MODEL_APPROVAL_V1",
    "get_approval_policy",
    "policy_version_ref",
]
