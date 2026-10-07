"""Phase 8E：Drift 分类 + ProductionDriftReport 组装。"""

from __future__ import annotations

from datetime import datetime, timezone

from .identity import build_report_id
from .protocol import (
    DriftFinding,
    DriftPolicyRecord,
    DriftSeverity,
    DriftType,
    MetricDeviation,
    MetricsSnapshot,
    PerformanceComparisonRun,
    ProductionDriftReport,
    ReturnAttribution,
)

_METRIC_TO_DRIFT: dict[str, DriftType] = {
    "shadow_drift": "SIGNAL_DRIFT",
    "signal_correlation": "SIGNAL_DRIFT",
    "qty_delta": "PORTFOLIO_DRIFT",
    "max_drawdown": "RISK_DRIFT",
    "slippage_bps": "SLIPPAGE_DRIFT",
    "total_cost_bps": "COST_DRIFT",
    "reject_rate": "EXECUTION_DRIFT",
    "turnover": "EXECUTION_DRIFT",
    "gross_exposure": "PORTFOLIO_DRIFT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _severity_for_metric(
    rule_metric: str,
    deviation: MetricDeviation,
    policy: DriftPolicyRecord,
) -> DriftSeverity:
    rule = next((r for r in policy.rules if r.metric == rule_metric), None)
    if rule is None:
        return "SKIP"
    magnitude = abs(deviation.delta)
    if rule_metric == "signal_correlation":
        magnitude = abs(1.0 - deviation.actual)
    if magnitude >= rule.critical_threshold:
        return "CRITICAL"
    if magnitude >= rule.warning_threshold:
        return "WARNING"
    return "OK"


def classify_drift(
    deviations: list[MetricDeviation],
    policy: DriftPolicyRecord,
    *,
    baseline: MetricsSnapshot,
    actual: MetricsSnapshot,
) -> tuple[list[DriftFinding], DriftSeverity]:
    """按 DriftPolicy 规则生成分类 Finding（无证据 → SKIP）。"""
    findings: list[DriftFinding] = []
    overall: DriftSeverity = "OK"
    rank = {"OK": 0, "SKIP": 0, "WARNING": 1, "CRITICAL": 2}
    by_metric = {d.metric: d for d in deviations}
    for rule in policy.rules:
        dev = by_metric.get(rule.metric)
        if dev is None:
            continue
        sev = _severity_for_metric(rule.metric, dev, policy)
        if sev == "SKIP":
            continue
        drift_type = _METRIC_TO_DRIFT.get(rule.metric, "MARKET_REGIME_DRIFT")
        if sev == "OK":
            continue
        findings.append(
            DriftFinding(
                drift_type=drift_type,
                severity=sev,
                metric=rule.metric,
                message=f"{rule.metric} breach: actual={dev.actual:.4f} baseline={dev.baseline:.4f}",
                evidence={
                    "delta": dev.delta,
                    "warning_threshold": rule.warning_threshold,
                    "critical_threshold": rule.critical_threshold,
                    "action": rule.action,
                },
            )
        )
        if rank[sev] > rank[overall]:
            overall = sev
    # 无规则覆盖时仍可对 inject 中 model/feature hash 差异留 SKIP
    if not findings and actual.extra.get("force_drift"):
        findings.append(
            DriftFinding(
                drift_type="MODEL_DRIFT",
                severity="WARNING",
                metric="force_drift",
                message="inject force_drift flag",
                evidence=dict(actual.extra),
            )
        )
        overall = "WARNING"
    return findings, overall


def build_drift_report(
    run: PerformanceComparisonRun,
    *,
    policy: DriftPolicyRecord,
    baseline_metrics: MetricsSnapshot,
    attribution: ReturnAttribution,
) -> ProductionDriftReport:
    findings, overall = classify_drift(
        run.deviations,
        policy,
        baseline=baseline_metrics,
        actual=run.actual_metrics,
    )
    return ProductionDriftReport(
        report_id=build_report_id(run_id=run.run_id),
        run_id=run.run_id,
        baseline_id=run.baseline_id,
        strategy_code=run.strategy_code,
        actual_source=run.actual_source,
        window_start=run.window_start,
        window_end=run.window_end,
        policy_content_hash=policy.policy_content_hash,
        deviations=run.deviations,
        findings=findings,
        attribution=attribution,
        overall_severity=overall,
        created_at=_now(),
    )


__all__ = ["build_drift_report", "classify_drift"]
