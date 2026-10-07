"""Phase 8C：CV Gate — cv_hash 对应 status 须 PASSED*。"""

from __future__ import annotations

from ..bridge_from_candidate import ValidationEvidenceContext
from ..protocol import GateCheckResult, ValidationPolicyRules

_PASSED_PREFIX = ("PASSED", "PASS", "OK")


def _cv_passed(status: str) -> bool:
    text = str(status or "").strip().upper()
    if not text:
        return False
    return any(text.startswith(p) for p in _PASSED_PREFIX)


def run_cv_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    status = str(ctx.cv_status or "")
    cand = ctx.candidate
    if not status and not cand.cv_hash:
        if policy.require_cv_passed:
            return GateCheckResult(
                check="cv",
                status="FAIL",
                reason="cv_hash missing and require_cv_passed",
                metrics={"cv_hash": cand.cv_hash},
            )
        return GateCheckResult(
            check="cv",
            status="SKIP",
            reason="no cv evidence; skipped",
        )
    if not status:
        return GateCheckResult(
            check="cv",
            status="FAIL" if policy.require_cv_passed else "SKIP",
            reason="cv status unknown",
            metrics={"cv_hash": cand.cv_hash},
        )
    if _cv_passed(status):
        return GateCheckResult(
            check="cv",
            status="PASS",
            reason="cross validation passed",
            metrics={"cv_status": status, "cv_hash": cand.cv_hash},
        )
    if policy.require_cv_passed:
        return GateCheckResult(
            check="cv",
            status="FAIL",
            reason=f"cv status not passed: {status}",
            metrics={"cv_status": status},
        )
    return GateCheckResult(
        check="cv",
        status="SKIP",
        reason=f"cv not passed but not required: {status}",
        metrics={"cv_status": status},
    )


__all__ = ["run_cv_check"]
