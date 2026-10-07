"""Model Evaluation Quality Gate。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import ModelEvaluationInject, ModelEvaluationPolicy, ModelEvaluationRequest


class QualityGateResult:
    def __init__(self, verdict: str, reasons: list[str] | None = None) -> None:
        self.verdict = verdict  # PASS | BLOCKED
        self.reasons = list(reasons or [])


def evaluate_quality_gate(
    request: ModelEvaluationRequest,
    *,
    policy: ModelEvaluationPolicy,
    version_lifecycle: str = "",
    artifact_status: str = "",
    inject: ModelEvaluationInject | None = None,
) -> QualityGateResult:
    reasons: list[str] = []
    inj = inject or ModelEvaluationInject()

    has_inject_preds = bool(inj.predictions)
    skip_art = bool(inj.skip_artifact_check or has_inject_preds)

    if version_lifecycle in ("DRAFT", "TRAINING"):
        reasons.append("model_version_not_ready")
    if not version_lifecycle and not has_inject_preds:
        reasons.append("model_version_not_ready")

    if not skip_art:
        if artifact_status and artifact_status != "AVAILABLE":
            reasons.append("artifact_not_available")
        if not artifact_status:
            reasons.append("artifact_status_missing")

    eval_hash = (request.evaluation_dataset_hash or request.dataset_hash or "").strip()
    if not eval_hash:
        reasons.append("evaluation_dataset_hash_missing")
    if not (request.evaluation_start and request.evaluation_end):
        reasons.append("evaluation_window_missing")

    known = dict(inj.known_hashes or {})
    for field, attr in (
        ("evaluation_dataset_hash", "evaluation_dataset_hash"),
        ("feature_set_hash", "feature_set_hash"),
        ("label_hash", "label_hash"),
        ("snapshot_id", "snapshot_id"),
    ):
        expected = known.get(field) or known.get(attr)
        if field == "evaluation_dataset_hash":
            actual = request.evaluation_dataset_hash or request.dataset_hash
        else:
            actual = getattr(request, attr, "") or ""
        if expected and actual and expected != actual:
            reasons.append(f"{field}_not_found")
        if expected and not actual:
            reasons.append(f"{field}_missing")

    if not has_inject_preds:
        if not (request.feature_set_hash or "").strip() and not known.get(
            "feature_set_hash"
        ):
            reasons.append("feature_set_hash_missing")
        if not (request.label_hash or "").strip() and not known.get("label_hash"):
            reasons.append("label_hash_missing")

    if policy.require_pit and inj.force_pit_fail:
        reasons.append("pit_violation")

    if reasons:
        return QualityGateResult("BLOCKED", reasons)
    return QualityGateResult("PASS", [])


def check_prediction_panel(rows: list[Mapping[str, Any]]) -> list[str]:
    """完整性启发式：空、NaN/Inf、重复 date+instrument。"""
    reasons: list[str] = []
    if not rows:
        reasons.append("predictions_empty")
        return reasons
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(rows):
        pred = row.get("prediction")
        if pred is None:
            reasons.append(f"prediction_null@{i}")
            continue
        try:
            f = float(pred)
            if f != f or f in (float("inf"), float("-inf")):
                reasons.append(f"prediction_nonfinite@{i}")
        except (TypeError, ValueError):
            reasons.append(f"prediction_invalid@{i}")
        key = (str(row.get("date") or ""), str(row.get("instrument") or ""))
        if key in seen:
            reasons.append(f"duplicate_key@{key[0]}|{key[1]}")
        seen.add(key)
    return reasons


__all__ = ["QualityGateResult", "check_prediction_panel", "evaluate_quality_gate"]
