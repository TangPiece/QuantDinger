"""Phase 8H：FeedbackQualityGate（PIT / completeness / lineage / duplicate / PnL 一致性）。"""

from __future__ import annotations

from typing import Mapping

from .protocol import FeedbackLineage, FeedbackRow, QualityGateResult


class QualityGateError(RuntimeError):
    pass


def _lineage_ok(lineage: FeedbackLineage) -> bool:
    if lineage.incident_id or lineage.comparison_run_id or lineage.alert_id:
        return True
    if lineage.dataset_hash or lineage.snapshot_id or lineage.strategy_version:
        return True
    return False


def evaluate_feedback_rows(
    rows: list[FeedbackRow],
    *,
    lineage: FeedbackLineage,
    pnl_total: float | None = None,
    require_pit: bool = True,
) -> QualityGateResult:
    reasons: list[str] = []
    if require_pit:
        if not any(str(r.as_of_time or "").strip() for r in rows):
            reasons.append("missing_pit_as_of_time")
    if not _lineage_ok(lineage):
        reasons.append("bad_lineage")
    seen: set[str] = set()
    for row in rows:
        key = f"{row.metric}|{row.as_of_time}|{row.source_artifact_id}"
        if key in seen:
            reasons.append(f"duplicate_row:{key}")
            break
        seen.add(key)
    if pnl_total is not None:
        metric_sum = sum(r.value for r in rows if r.metric == "pnl_component")
        if rows and abs(metric_sum - float(pnl_total)) > 1e-6:
            reasons.append("pnl_position_inconsistent")
    if reasons:
        return QualityGateResult(verdict="REJECT", reasons=reasons)
    return QualityGateResult(verdict="PASS")


def assert_quality_gate(result: QualityGateResult) -> None:
    if result.verdict != "PASS":
        raise QualityGateError("; ".join(result.reasons) or "quality_gate_rejected")


def gate_from_inject(section: Mapping[str, object]) -> QualityGateResult:
    """Fake inject 可注入 gate_overrides（测试违规路径）。"""
    override = section.get("gate_override")
    if isinstance(override, dict):
        verdict = str(override.get("verdict") or "PASS").upper()
        reasons = list(override.get("reasons") or [])
        if verdict == "REJECT":
            return QualityGateResult(verdict="REJECT", reasons=[str(x) for x in reasons])
    return QualityGateResult(verdict="PASS")


__all__ = [
    "QualityGateError",
    "assert_quality_gate",
    "evaluate_feedback_rows",
    "gate_from_inject",
]
