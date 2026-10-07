"""Phase 8C：风险 Gate — max_drawdown / exposure 阈值。"""

from __future__ import annotations

from ..bridge_from_candidate import ValidationEvidenceContext
from ..protocol import GateCheckResult, ValidationPolicyRules


def run_risk_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    m = ctx.metrics
    dd = m.get("max_drawdown")
    if dd is None:
        dd = m.get("max_dd")
    try:
        max_dd = abs(float(dd)) if dd is not None else 0.0
    except (TypeError, ValueError):
        max_dd = 0.0
    if max_dd == 0.0:
        return GateCheckResult(
            check="risk",
            status="SKIP",
            reason="max_drawdown not in metrics",
        )
    if max_dd > policy.max_drawdown:
        return GateCheckResult(
            check="risk",
            status="FAIL",
            reason="max_drawdown above policy",
            metrics={"max_drawdown": max_dd, "limit": policy.max_drawdown},
        )
    exposure = m.get("max_exposure")
    if exposure is not None:
        try:
            exp = float(exposure)
            if exp > 1.05:
                return GateCheckResult(
                    check="risk",
                    status="FAIL",
                    reason="max_exposure above 105%",
                    metrics={"max_exposure": exp},
                )
        except (TypeError, ValueError):
            pass
    return GateCheckResult(
        check="risk",
        status="PASS",
        metrics={"max_drawdown": max_dd},
    )


__all__ = ["run_risk_check"]
