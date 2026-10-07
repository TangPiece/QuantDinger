"""Phase 8C：从 StrategyCandidate 只读加载 Gate 证据（支持 inject 供 CI）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry
from app.services.strategy_candidate.protocol import StrategyCandidateRecord


@dataclass
class ValidationEvidenceContext:
    """Gate 输入快照；不修改 Candidate lineage。"""

    candidate: StrategyCandidateRecord
    metrics: dict[str, Any] = field(default_factory=dict)
    cv_status: str = ""
    pit_signals: list[dict[str, Any]] = field(default_factory=list)
    pit_leak_ratio: float = 0.0
    feature_leakage: float = 0.0
    capacity_ctx: dict[str, Any] = field(default_factory=dict)
    stability_windows: list[dict[str, Any]] = field(default_factory=list)
    inject_used: bool = False


def _merge_metrics(
    base: Mapping[str, Any] | None,
    inject: Mapping[str, Any] | None,
) -> dict[str, Any]:
    out = dict(base or {})
    if inject:
        out.update(dict(inject))
    return out


def build_evidence_context(
    registry: ResearchRegistry,
    candidate: StrategyCandidateRecord,
    *,
    inject: Mapping[str, Any] | None = None,
) -> ValidationEvidenceContext:
    """从 Registry backtest/CV 摘要 + inject 组装证据；默认不重算 Qlib。"""
    inj = dict(inject or {})
    metrics: dict[str, Any] = {}
    cv_status = str(inj.get("cv_status") or "")

    if candidate.backtest_hash:
        try:
            bt = registry.get_research_backtest(candidate.backtest_hash)
            metrics = _merge_metrics(bt.metrics_json, inj.get("metrics"))
            if not cv_status:
                cv_status = str((bt.metadata or {}).get("cv_status") or "")
        except Exception:
            metrics = _merge_metrics(None, inj.get("metrics"))
    else:
        metrics = _merge_metrics(None, inj.get("metrics"))

    if candidate.cv_hash and not cv_status:
        try:
            cv = registry.get_research_cross_validation(candidate.cv_hash)
            cv_status = str(cv.status or "")
            if not metrics and cv.metrics_side_by_side_json:
                metrics = _merge_metrics(cv.metrics_side_by_side_json, inj.get("metrics"))
        except Exception:
            pass

    if inj.get("cv_status"):
        cv_status = str(inj["cv_status"])

    pit_signals = list(inj.get("pit_signals") or [])
    capacity_ctx = dict(inj.get("capacity") or {})
    stability_windows = list(inj.get("stability_windows") or [])

    return ValidationEvidenceContext(
        candidate=candidate,
        metrics=metrics,
        cv_status=cv_status,
        pit_signals=pit_signals,
        pit_leak_ratio=float(inj.get("pit_leak_ratio") or 0.0),
        feature_leakage=float(inj.get("feature_leakage") or 0.0),
        capacity_ctx=capacity_ctx,
        stability_windows=stability_windows,
        inject_used=bool(inj),
    )


__all__ = ["ValidationEvidenceContext", "build_evidence_context"]
