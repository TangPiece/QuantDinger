"""Model Evaluation Policy 预设。"""

from __future__ import annotations

from .protocol import ModelEvaluationPolicy

MODEL_STANDARD_V1 = ModelEvaluationPolicy(
    policy_code="MODEL_STANDARD_V1",
    version="1.0.0",
    name="Model Standard Evaluation V1",
    ranking_ks=[10, 20, 50],
    min_cross_section=3,
    require_pit=True,
)

_PRESETS: dict[str, ModelEvaluationPolicy] = {
    "MODEL_STANDARD_V1": MODEL_STANDARD_V1,
}


def get_policy_preset(policy_code: str) -> ModelEvaluationPolicy:
    key = (policy_code or "MODEL_STANDARD_V1").strip() or "MODEL_STANDARD_V1"
    if key not in _PRESETS:
        raise KeyError(f"unknown model evaluation policy: {policy_code}")
    return _PRESETS[key].model_copy(deep=True)


__all__ = ["MODEL_STANDARD_V1", "get_policy_preset"]
