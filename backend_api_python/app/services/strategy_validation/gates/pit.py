"""Phase 8C：PIT / Leakage Gate（复用 5E pit_diff；inject 供 golden）。"""

from __future__ import annotations

from app.services.research_data.cross_validation.pit_diff import diff_pit

from ..bridge_from_candidate import ValidationEvidenceContext
from ..protocol import GateCheckResult, ValidationPolicyRules


def run_leakage_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    """特征 / 汇总泄漏比率（inject 或 metrics 字段）。"""
    ratio = float(ctx.feature_leakage or ctx.metrics.get("feature_leakage") or 0.0)
    leak_ratio = float(ctx.pit_leak_ratio or ctx.metrics.get("pit_leakage_ratio") or 0.0)
    combined = max(ratio, leak_ratio)
    if combined > policy.max_feature_leakage and combined > policy.max_pit_leakage_ratio:
        # 分别校验：任一超阈即 FAIL
        pass
    if ratio > policy.max_feature_leakage:
        return GateCheckResult(
            check="leakage",
            status="FAIL",
            reason="feature_leakage above policy",
            metrics={"feature_leakage": ratio, "max": policy.max_feature_leakage},
        )
    if leak_ratio > policy.max_pit_leakage_ratio:
        return GateCheckResult(
            check="leakage",
            status="FAIL",
            reason="pit_leakage_ratio above policy",
            metrics={"pit_leakage_ratio": leak_ratio, "max": policy.max_pit_leakage_ratio},
        )
    return GateCheckResult(
        check="leakage",
        status="PASS",
        reason="no leakage over threshold",
        metrics={"feature_leakage": ratio, "pit_leakage_ratio": leak_ratio},
    )


def run_pit_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    _ = policy
    layer = diff_pit(ctx.pit_signals or None)
    status_map = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}
    gate_status = status_map.get(str(layer.status or "FAIL"), "FAIL")
    return GateCheckResult(
        check="pit",
        status=gate_status,  # type: ignore[arg-type]
        reason=str(layer.message or ""),
        metrics={"layer": layer.model_dump(mode="json")},
    )


__all__ = ["run_leakage_check", "run_pit_check"]
