"""Reproducibility Policy 预设。"""

from __future__ import annotations

from .protocol import ReproducibilityPolicy

REPRO_STRICT_V1 = ReproducibilityPolicy(
    policy_code="REPRO_STRICT_V1",
    version="1.0.0",
    name="Reproducibility Strict V1",
    mode="STRICT",
    metric_tolerance=0.0,
    prediction_tolerance=0.0,
    artifact_match_required=True,
    environment_match_required=True,
    dependency_match_required=True,
    dataset_match_required=True,
    code_match_required=True,
    seed_match_required=True,
)

REPRO_NUMERICAL_V1 = ReproducibilityPolicy(
    policy_code="REPRO_NUMERICAL_V1",
    version="1.0.0",
    name="Reproducibility Numerical V1",
    mode="REPRODUCIBLE",
    metric_tolerance=1e-4,
    prediction_tolerance=1e-6,
    artifact_match_required=False,
    environment_match_required=True,
    dependency_match_required=True,
    dataset_match_required=True,
    code_match_required=True,
    seed_match_required=True,
)

REPRO_AUDITABLE_V1 = ReproducibilityPolicy(
    policy_code="REPRO_AUDITABLE_V1",
    version="1.0.0",
    name="Reproducibility Auditable V1",
    mode="AUDITABLE",
    metric_tolerance=1.0,
    prediction_tolerance=1.0,
    artifact_match_required=False,
    environment_match_required=False,
    dependency_match_required=False,
    dataset_match_required=True,
    code_match_required=True,
    seed_match_required=False,
)

_PRESETS: dict[str, ReproducibilityPolicy] = {
    "REPRO_STRICT_V1": REPRO_STRICT_V1,
    "REPRO_NUMERICAL_V1": REPRO_NUMERICAL_V1,
    "REPRO_AUDITABLE_V1": REPRO_AUDITABLE_V1,
}


def get_policy_preset(policy_code: str = "REPRO_STRICT_V1") -> ReproducibilityPolicy:
    key = (policy_code or "REPRO_STRICT_V1").strip() or "REPRO_STRICT_V1"
    if key not in _PRESETS:
        raise KeyError(f"unknown reproducibility policy: {policy_code}")
    return _PRESETS[key].model_copy(deep=True)


def policy_version_ref(policy: ReproducibilityPolicy) -> str:
    return f"{policy.policy_code}@{policy.version}"


__all__ = [
    "REPRO_AUDITABLE_V1",
    "REPRO_NUMERICAL_V1",
    "REPRO_STRICT_V1",
    "get_policy_preset",
    "policy_version_ref",
]
