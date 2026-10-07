"""Phase 8D：前置校验（Validation PASSED、lineage、Policy 指标）。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .protocol import PromotionPolicyRules, PromotionRequest


class PreconditionError(RuntimeError):
    """晋升前置不满足。"""


def _metric(inject: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    raw = inject.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def check_runtime_metrics(
    rules: PromotionPolicyRules,
    *,
    to_environment: str,
    inject: Mapping[str, Any] | None,
) -> None:
    """Shadow/CL/LIVE 指标门槛；CI 用 inject 满足。"""
    data = dict(inject or {})
    dst = str(to_environment).upper()
    if dst == "SHADOW":
        return
    if dst in ("CONTROLLED_LIVE", "LIVE"):
        if _metric(data, "shadow_days") < rules.min_shadow_days:
            raise PreconditionError("min_shadow_days not met")
        if _metric(data, "shadow_drawdown") > rules.max_shadow_drawdown:
            raise PreconditionError("max_shadow_drawdown exceeded")
        if _metric(data, "shadow_drift") > rules.max_shadow_drift:
            raise PreconditionError("max_shadow_drift exceeded")
        if int(data.get("recon_errors", 0)) > rules.max_recon_errors:
            raise PreconditionError("max_recon_errors exceeded")
    if dst == "LIVE":
        if _metric(data, "controlled_days") < rules.min_controlled_days:
            raise PreconditionError("min_controlled_days not met")
        if _metric(data, "live_drawdown") > rules.max_live_drawdown:
            raise PreconditionError("max_live_drawdown exceeded")
        if _metric(data, "slippage") > rules.max_slippage:
            raise PreconditionError("max_slippage exceeded")
        if _metric(data, "reject_rate") > rules.max_reject_rate:
            raise PreconditionError("max_reject_rate exceeded")
        if int(data.get("risk_breach", 0)) > rules.max_risk_breach:
            raise PreconditionError("max_risk_breach exceeded")


def assert_validation_passed(
    registry: ResearchRegistry,
    *,
    validation_id: str,
    candidate_id: str,
) -> None:
    """钉死 validation_id 且 status=PASSED。"""
    vid = str(validation_id).strip()
    if not vid:
        raise PreconditionError("validation_id required")
    try:
        row = registry.get_strategy_validation_run(vid)
    except Exception as exc:
        raise PreconditionError(f"validation run not found: {vid}") from exc
    if str(row.candidate_id) != str(candidate_id).strip():
        raise PreconditionError("validation_id candidate mismatch")
    if str(row.status or "").upper() != "PASSED":
        raise PreconditionError("validation run must be PASSED")


def assert_lineage_match(
    *,
    candidate_content_hash: str,
    registry_content_hash: str,
) -> None:
    """Candidate 与 Registry version content_hash 须一致。"""
    c = str(candidate_content_hash or "").strip()
    r = str(registry_content_hash or "").strip()
    if not c or not r:
        raise PreconditionError("content_hash pin missing")
    if c != r:
        raise PreconditionError("lineage content_hash mismatch → INVALID")


def assert_request_lineage_unchanged(
    request: PromotionRequest,
    *,
    candidate_content_hash: str,
    registry_content_hash: str,
) -> None:
    """执行时 content_hash 与请求钉扎一致。"""
    if str(request.content_hash) != str(candidate_content_hash).strip():
        raise PreconditionError("candidate lineage changed since request")
    if str(request.content_hash) != str(registry_content_hash).strip():
        raise PreconditionError("registry version lineage changed since request")


def infer_current_environment(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    governance: Any | None = None,
) -> str:
    """从最近完成 Run 或 Governance lifecycle 推断当前环境。"""
    code = str(strategy_code).strip()
    try:
        runs = registry.list_strategy_promotion_runs(strategy_code=code)
    except Exception:
        runs = []
    completed = [
        r
        for r in runs
        if str(getattr(r, "status", "")) == "COMPLETED"
    ]
    if completed:
        completed.sort(key=lambda r: getattr(r, "completed_at", "") or "")
        return str(getattr(completed[-1], "to_environment", "REGISTERED") or "REGISTERED")

    if governance is not None:
        from app.services.strategy_registry.identity import strategy_id_from_code

        sid = strategy_id_from_code(code)
        lc = getattr(governance, "_lifecycle", {}).get(sid)
        if lc is not None:
            state = str(getattr(lc, "state", "") or "").upper()
            if state == "SHADOW":
                return "SHADOW"
            if state == "CONTROLLED_LIVE":
                return "CONTROLLED_LIVE"
            if state == "LIVE":
                return "LIVE"
    return "REGISTERED"


__all__ = [
    "PreconditionError",
    "assert_lineage_match",
    "assert_request_lineage_unchanged",
    "assert_validation_passed",
    "check_runtime_metrics",
    "infer_current_environment",
]
