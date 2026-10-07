"""Phase 8C：Strategy Validation Gate 契约（只读 Candidate，非 Shadow/LIVE）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_strategy_validation@1"

ValidationRunStatus = Literal["VALIDATING", "PASSED", "FAILED", "CONDITIONAL"]
GateCheckStatus = Literal["PASS", "FAIL", "SKIP"]
OverallValidationStatus = Literal["PASSED", "FAILED", "CONDITIONAL"]


class _ValModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GateCheckResult(_ValModel):
    """单层 Gate 检查结果。"""

    check: str
    status: GateCheckStatus
    metrics: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ValidationResult(_ValModel):
    """结构化 Validation 报告（写入 R2 result.json）。"""

    overall_status: OverallValidationStatus
    leakage_check: GateCheckResult
    pit_check: GateCheckResult
    oos_check: GateCheckResult
    overfit_check: GateCheckResult
    cost_check: GateCheckResult
    capacity_check: GateCheckResult
    risk_check: GateCheckResult
    stability_check: GateCheckResult
    lineage_check: GateCheckResult


class ValidationPolicyRules(_ValModel):
    """版本化准入规则；变更须 bump policy_content_hash。"""

    max_pit_leakage_ratio: float = 0.0
    max_feature_leakage: float = 0.0
    min_oos_sharpe: float = 0.0
    max_drawdown: float = 0.35
    max_turnover: float = 5.0
    max_slippage_bps: float = 50.0
    min_capacity_notional: float = 0.0
    max_participation_rate: float = 0.25
    require_cv_passed: bool = True
    require_net_backtest: bool = True
    max_is_oos_sharpe_gap: float = 0.8
    stability_min_windows_pass: float = 0.6
    allow_recompute: bool = False
    capacity_soft_fail: bool = True


class ValidationPolicyRecord(_ValModel):
    """ValidationPolicy SSOT（D1 索引 + rules 钉扎）。"""

    policy_id: str
    policy_version: str
    policy_content_hash: str
    rules: ValidationPolicyRules
    engine_version: str = ENGINE_VERSION
    description: str = ""


class ValidationRunRecord(_ValModel):
    """不可变 ValidationRun（8B VALIDATED ≠ PASSED）。"""

    validation_id: str
    candidate_id: str
    candidate_version: str
    dataset_hash: str = ""
    snapshot_id: str = ""
    policy_id: str
    policy_version: str
    policy_content_hash: str
    validator_version: str = ENGINE_VERSION
    started_at: str = ""
    completed_at: str = ""
    status: ValidationRunStatus = "VALIDATING"
    operator: str = ""
    storage_uri: str = ""
    result: ValidationResult | None = None


__all__ = [
    "ENGINE_VERSION",
    "GateCheckResult",
    "GateCheckStatus",
    "OverallValidationStatus",
    "ValidationPolicyRecord",
    "ValidationPolicyRules",
    "ValidationResult",
    "ValidationRunRecord",
    "ValidationRunStatus",
]
