"""Phase 8E：内置 DriftPolicy preset（default_drift_v1）。"""

from __future__ import annotations

from .pin import policy_content_hash
from .protocol import DriftPolicyRecord, DriftPolicyRule

DEFAULT_DRIFT_POLICY_ID = "default_drift_v1"
DEFAULT_POLICY_VERSION = "v1"


def _default_rules() -> list[DriftPolicyRule]:
    return [
        DriftPolicyRule(
            metric="shadow_drift",
            window="7d",
            warning_threshold=0.08,
            critical_threshold=0.15,
        ),
        DriftPolicyRule(
            metric="max_drawdown",
            window="7d",
            warning_threshold=0.12,
            critical_threshold=0.2,
        ),
        DriftPolicyRule(
            metric="slippage_bps",
            window="7d",
            warning_threshold=25.0,
            critical_threshold=45.0,
        ),
        DriftPolicyRule(
            metric="signal_correlation",
            window="7d",
            warning_threshold=0.15,
            critical_threshold=0.3,
        ),
        DriftPolicyRule(
            metric="qty_delta",
            window="7d",
            warning_threshold=0.1,
            critical_threshold=0.25,
        ),
    ]


def default_drift_v1() -> DriftPolicyRecord:
    pid = DEFAULT_DRIFT_POLICY_ID
    pver = DEFAULT_POLICY_VERSION
    rules = _default_rules()
    return DriftPolicyRecord(
        policy_id=pid,
        policy_version=pver,
        policy_content_hash=policy_content_hash(
            policy_id=pid, policy_version=pver, rules=rules
        ),
        rules=rules,
        description="默认生产漂移观察策略（仅 ALERT）",
    )


def get_default_preset() -> DriftPolicyRecord:
    return default_drift_v1().model_copy(deep=True)


__all__ = [
    "DEFAULT_DRIFT_POLICY_ID",
    "DEFAULT_POLICY_VERSION",
    "default_drift_v1",
    "get_default_preset",
]
