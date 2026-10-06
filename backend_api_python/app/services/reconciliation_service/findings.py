"""Finding 状态机：OPEN→ACKNOWLEDGED→INVESTIGATING→RESOLVED|WAIVED。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .hash import derive_finding_id
from .protocol import (
    FindingSeverity,
    FindingStatus,
    FindingType,
    ReconciliationFinding,
)

# 合法迁移；CRITICAL 禁止进入 WAIVED（见 transition）
_TRANSITIONS: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "WAIVED"}),
    "ACKNOWLEDGED": frozenset({"INVESTIGATING", "RESOLVED", "WAIVED"}),
    "INVESTIGATING": frozenset({"RESOLVED", "WAIVED", "ACKNOWLEDGED"}),
    "RESOLVED": frozenset(),
    "WAIVED": frozenset(),
}


class FindingsError(RuntimeError):
    """Finding 生命周期非法操作。"""


def assert_transition(current: str, target: str) -> None:
    """校验 Finding 状态迁移。"""
    allowed = _TRANSITIONS.get(str(current).upper(), frozenset())
    if str(target).upper() not in allowed:
        raise FindingsError(
            f"illegal finding transition {current!r} → {target!r}"
        )


def make_finding(
    *,
    run_id: str,
    finding_type: FindingType,
    severity: FindingSeverity,
    entity_type: str,
    entity_id: str,
    expected: Mapping[str, Any] | None = None,
    actual: Mapping[str, Any] | None = None,
    difference: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    salt: str = "",
) -> ReconciliationFinding:
    """构造 OPEN Finding。"""
    now = datetime.now(timezone.utc).isoformat()
    fid = derive_finding_id(
        run_id, finding_type=finding_type, entity_id=entity_id, salt=salt
    )
    return ReconciliationFinding(
        finding_id=fid,
        run_id=run_id,
        type=finding_type,
        severity=severity,
        status="OPEN",
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity_id,
        expected=dict(expected or {}),
        actual=dict(actual or {}),
        difference=dict(difference or {}),
        detected_at=now,
        metadata=dict(metadata or {}),
    )


def transition(
    finding: ReconciliationFinding,
    target: FindingStatus,
    *,
    note: str = "",
) -> ReconciliationFinding:
    """推进 Finding 状态；CRITICAL 禁止 WAIVED。"""
    tgt = str(target).upper()
    if tgt == "WAIVED" and str(finding.severity).upper() == "CRITICAL":
        raise FindingsError("CRITICAL findings cannot be waived")
    assert_transition(finding.status, tgt)
    updates: dict[str, Any] = {"status": tgt}
    meta = dict(finding.metadata or {})
    if note:
        meta["last_note"] = note
    updates["metadata"] = meta
    if tgt in ("RESOLVED", "WAIVED"):
        updates["resolved_at"] = datetime.now(timezone.utc).isoformat()
    return finding.model_copy(update=updates)


def acknowledge(
    finding: ReconciliationFinding, *, note: str = ""
) -> ReconciliationFinding:
    return transition(finding, "ACKNOWLEDGED", note=note)


def investigate(
    finding: ReconciliationFinding, *, note: str = ""
) -> ReconciliationFinding:
    return transition(finding, "INVESTIGATING", note=note)


def resolve(
    finding: ReconciliationFinding, *, note: str = ""
) -> ReconciliationFinding:
    return transition(finding, "RESOLVED", note=note)


def waive(
    finding: ReconciliationFinding, *, note: str = ""
) -> ReconciliationFinding:
    """非 CRITICAL 可 Waive；CRITICAL 抛 FindingsError。"""
    return transition(finding, "WAIVED", note=note)
