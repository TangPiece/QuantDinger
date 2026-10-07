"""ApprovalGate：Evaluation PASS + Artifact AVAILABLE → APPROVED|REJECTED。"""

from __future__ import annotations

from typing import Any, Mapping

from .approval_policy import MODEL_APPROVAL_V1, get_approval_policy, policy_version_ref
from .protocol import (
    ApprovalGateResult,
    ModelApprovalPolicy,
    ModelArtifact,
    ModelPlatformInject,
    ModelVersion,
)


class ApprovalException(ValueError):
    """门控失败；禁止静默绕过（仅 inject.skip_approval_gate 供单测）。"""


def _predictive_metrics(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    raw = getattr(result, "raw_metrics", None) or {}
    if isinstance(raw, dict):
        pred = raw.get("predictive") or {}
        if isinstance(pred, dict):
            return dict(pred)
    return {}


def _metric_float(metrics: Mapping[str, Any], key: str) -> float | None:
    val = metrics.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def evaluate_approval_gate(
    *,
    version: ModelVersion,
    evaluation_run: Any | None,
    artifact: ModelArtifact | None,
    policy: ModelApprovalPolicy | None = None,
    inject: ModelPlatformInject | None = None,
    verify_checksum: bool = True,
    checksum_ok: bool | None = None,
) -> ApprovalGateResult:
    """评估是否可批。WARNING overall 默认 REJECT（policy 可放宽）。"""
    pol = policy or MODEL_APPROVAL_V1
    if inject and inject.skip_approval_gate:
        return ApprovalGateResult(
            verdict="PASS",
            reasons=[],
            evaluation_run_id=getattr(evaluation_run, "evaluation_run_id", "") or "",
            overall_status="PASS",
            policy_version=policy_version_ref(pol),
            artifact_id=artifact.artifact_id if artifact else version.artifact_id,
            metrics_snapshot={"skipped": True},
        )

    reasons: list[str] = []
    eval_id = ""
    overall = ""
    metrics_snap: dict[str, Any] = {}

    if version.lifecycle in ("DRAFT", "TRAINING"):
        reasons.append(f"lifecycle_blocked_{version.lifecycle}")

    if pol.require_lineage_hashes:
        for field in (
            "dataset_hash",
            "feature_set_hash",
            "label_hash",
            "model_config_hash",
            "version_content_hash",
        ):
            if not (getattr(version, field, None) or "").strip():
                reasons.append(f"lineage_missing_{field}")

    if evaluation_run is None:
        reasons.append("evaluation_missing")
    else:
        eval_id = str(getattr(evaluation_run, "evaluation_run_id", "") or "")
        status = str(getattr(evaluation_run, "status", "") or "")
        if pol.require_eval_succeeded and status != "SUCCEEDED":
            reasons.append(f"evaluation_status_{status or 'unknown'}")
        result = getattr(evaluation_run, "result", None)
        overall = str(getattr(result, "overall_status", "") or "") if result else ""
        if not overall:
            reasons.append("overall_status_missing")
        elif overall not in set(pol.allowed_overall_status or []):
            reasons.append(f"overall_status_{overall}_not_allowed")
        metrics_snap = _predictive_metrics(result)
        if pol.require_pit and result is not None:
            quality = str(getattr(result, "quality_status", "") or "")
            # quality FAIL implies PIT/quality gate failed in 9F-6
            if quality == "FAIL":
                reasons.append("pit_or_quality_fail")
        for key, threshold in (
            ("mean_ic", pol.min_mean_ic),
            ("mean_rank_ic", pol.min_mean_rank_ic),
            ("ic_ir", pol.min_ic_ir),
        ):
            if threshold is None:
                continue
            val = _metric_float(metrics_snap, key)
            if val is None or val < float(threshold):
                reasons.append(f"metric_{key}_below_threshold")

    art_id = ""
    if pol.require_artifact_available:
        if artifact is None:
            reasons.append("artifact_missing")
        else:
            art_id = artifact.artifact_id
            if artifact.status != "AVAILABLE":
                reasons.append(f"artifact_status_{artifact.status}")
            if verify_checksum:
                ok = checksum_ok
                if ok is None:
                    cs = (artifact.checksum or "").strip()
                    ok = len(cs) >= 32
                if not ok:
                    reasons.append("artifact_checksum_invalid")

    verdict = "PASS" if not reasons else "REJECT"
    return ApprovalGateResult(
        verdict=verdict,
        reasons=reasons,
        evaluation_run_id=eval_id,
        overall_status=overall,
        policy_version=policy_version_ref(pol),
        artifact_id=art_id or (artifact.artifact_id if artifact else ""),
        metrics_snapshot=metrics_snap,
    )


def assert_approval_pass(result: ApprovalGateResult) -> None:
    if result.verdict != "PASS":
        raise ApprovalException("; ".join(result.reasons) or "approval_rejected")


def resolve_policy(
    policy_code: str = "MODEL_APPROVAL_V1",
    *,
    policy: ModelApprovalPolicy | None = None,
) -> ModelApprovalPolicy:
    if policy is not None:
        return policy
    return get_approval_policy(policy_code)


__all__ = [
    "ApprovalException",
    "assert_approval_pass",
    "evaluate_approval_gate",
    "resolve_policy",
]
