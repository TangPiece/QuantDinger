"""Phase 8C：内置 ValidationPolicy preset（default_research_v1）。"""

from __future__ import annotations

from .pin import policy_content_hash
from .protocol import ValidationPolicyRecord, ValidationPolicyRules

DEFAULT_RESEARCH_V1_ID = "default_research_v1"
DEFAULT_RESEARCH_V1_VERSION = "v1"

_DEFAULT_RULES = ValidationPolicyRules(
    max_pit_leakage_ratio=0.0,
    max_feature_leakage=0.0,
    min_oos_sharpe=0.3,
    max_drawdown=0.35,
    max_turnover=4.0,
    max_slippage_bps=40.0,
    min_capacity_notional=100_000.0,
    max_participation_rate=0.2,
    require_cv_passed=True,
    require_net_backtest=True,
    max_is_oos_sharpe_gap=0.75,
    stability_min_windows_pass=0.6,
    allow_recompute=False,
    capacity_soft_fail=True,
)


def default_research_v1() -> ValidationPolicyRecord:
    """研究默认准入策略 v1。"""
    pid = DEFAULT_RESEARCH_V1_ID
    pver = DEFAULT_RESEARCH_V1_VERSION
    rules = _DEFAULT_RULES.model_copy(deep=True)
    return ValidationPolicyRecord(
        policy_id=pid,
        policy_version=pver,
        policy_content_hash=policy_content_hash(
            policy_id=pid, policy_version=pver, rules=rules
        ),
        rules=rules,
        description="Phase 8C 研究侧默认 Validation Gate",
    )


_PRESETS: dict[tuple[str, str], ValidationPolicyRecord] = {
    (DEFAULT_RESEARCH_V1_ID, DEFAULT_RESEARCH_V1_VERSION): default_research_v1(),
}


def get_preset(policy_id: str, policy_version: str | None = None) -> ValidationPolicyRecord:
    """按 id/version 解析 preset；version 缺省取 v1。"""
    pid = str(policy_id or "").strip().lower()
    pver = str(policy_version or DEFAULT_RESEARCH_V1_VERSION).strip()
    key = (pid, pver)
    if key not in _PRESETS:
        raise KeyError(f"unknown validation policy preset: {pid}@{pver}")
    return _PRESETS[key].model_copy(deep=True)


def list_presets() -> list[ValidationPolicyRecord]:
    return [p.model_copy(deep=True) for p in _PRESETS.values()]


__all__ = [
    "DEFAULT_RESEARCH_V1_ID",
    "DEFAULT_RESEARCH_V1_VERSION",
    "default_research_v1",
    "get_preset",
    "list_presets",
]
