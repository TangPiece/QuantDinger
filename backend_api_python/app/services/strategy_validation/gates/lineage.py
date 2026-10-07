"""Phase 8C：Lineage Gate — Candidate 已冻结且 pin 一致。"""

from __future__ import annotations

from ..bridge_from_candidate import ValidationEvidenceContext
from ..protocol import GateCheckResult, ValidationPolicyRules


def run_lineage_check(
    ctx: ValidationEvidenceContext,
    policy: ValidationPolicyRules,
) -> GateCheckResult:
    _ = policy
    cand = ctx.candidate
    if cand.status not in ("READY_FOR_VALIDATION", "VALIDATED"):
        return GateCheckResult(
            check="lineage",
            status="FAIL",
            reason=f"candidate status {cand.status} not eligible for gate",
            metrics={"status": cand.status},
        )
    if not cand.lineage_frozen:
        return GateCheckResult(
            check="lineage",
            status="FAIL",
            reason="lineage not frozen",
            metrics={"lineage_frozen": cand.lineage_frozen},
        )
    if not cand.content_hash:
        return GateCheckResult(
            check="lineage",
            status="FAIL",
            reason="missing content_hash",
        )
    return GateCheckResult(
        check="lineage",
        status="PASS",
        reason="candidate lineage frozen and pinned",
        metrics={
            "content_hash": cand.content_hash,
            "dataset_hash": cand.dataset_hash,
            "candidate_version": cand.candidate_version,
        },
    )


__all__ = ["run_lineage_check"]
