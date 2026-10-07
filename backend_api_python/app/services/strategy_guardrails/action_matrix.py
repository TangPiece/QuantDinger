"""Phase 8G：内置 Action Matrix 查找（Monitoring 发现 → 建议动作）。"""

from __future__ import annotations

from .protocol import ActionMatrixEntry, BreachSignal, GuardrailActionType


def default_action_matrix() -> list[ActionMatrixEntry]:
    """preset default_guardrail_v1 与计划表一致。"""
    rows: list[tuple[str, str, GuardrailActionType, str, str]] = [
        ("EXECUTION", "CRITICAL", "THROTTLE", "slippage_bps", "滑点 CRITICAL → 限流"),
        ("EXECUTION", "CRITICAL", "THROTTLE", "reject_rate", "拒单 CRITICAL → 限流"),
        ("CAPACITY", "CRITICAL", "THROTTLE", "capacity_util", "容量 CRITICAL → 限流"),
        ("RISK", "CRITICAL", "PAUSE", "", "Risk CRITICAL → 暂停新单节奏"),
        ("RISK", "EMERGENCY", "SAFETY_STOP", "", "Risk EMERGENCY → Safety Stop"),
        ("RECONCILIATION", "CRITICAL", "PAUSE", "", "对账 CRITICAL → 暂停"),
        ("RECONCILIATION", "EMERGENCY", "SAFETY_STOP", "", "对账 EMERGENCY → Safety Stop"),
        ("MARKET_DATA", "CRITICAL", "PAUSE", "", "行情 CRITICAL → 暂停"),
        ("MARKET_DATA", "EMERGENCY", "SAFETY_STOP", "", "行情 EMERGENCY → Safety Stop"),
        ("PERFORMANCE", "CRITICAL", "REVIEW", "", "绩效 CRITICAL → 人工复核"),
        ("PERFORMANCE", "EMERGENCY", "REVIEW", "", "绩效 EMERGENCY → 人工复核"),
        ("SIGNAL", "CRITICAL", "REVIEW", "", "信号 CRITICAL → 人工复核"),
        ("SIGNAL", "EMERGENCY", "REVIEW", "", "信号 EMERGENCY → 人工复核"),
    ]
    return [
        ActionMatrixEntry(
            category=cat,
            severity=sev,
            action=act,
            metric=metric,
            description=desc,
        )
        for cat, sev, act, metric, desc in rows
    ]


def lookup_action(
    matrix: list[ActionMatrixEntry],
    breach: BreachSignal,
) -> GuardrailActionType | None:
    cat = str(breach.category or "").strip().upper()
    sev = str(breach.severity or "").strip().upper()
    metric = str(breach.metric or "").strip()
    best: GuardrailActionType | None = None
    for row in matrix:
        if row.category.upper() != cat or row.severity.upper() != sev:
            continue
        if row.metric and row.metric != metric:
            continue
        best = row.action
        if row.metric:
            return best
    if best is not None:
        return best
    if sev == "EMERGENCY" and cat in ("RISK", "RECONCILIATION", "MARKET_DATA"):
        return "SAFETY_STOP"
    if sev == "CRITICAL" and cat in ("PERFORMANCE", "SIGNAL"):
        return "REVIEW"
    return None


__all__ = ["default_action_matrix", "lookup_action"]
