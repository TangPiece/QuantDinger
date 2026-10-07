"""Phase 8D：StrategyPromotionService 门面（无 auto LIVE / OMS）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry
from app.services.trading_governance.approval import hash_approval_token

from .bridge_from_candidate import BridgeFromCandidateError, load_promotion_context
from .bridge_to_governance import apply_governance_for_target
from .bridge_to_registry import bind_registry_version
from .bridge_to_runtime import open_controlled_live_session, open_shadow_session
from .fsm import InvalidPromotionTransitionError, assert_environment_transition, stages_for_transition
from .identity import build_pipeline_run_id, build_request_id, normalize_idempotency_key
from .lock import PromotionLock, PromotionLockError
from .policy import resolve_policy_for_transition
from .preconditions import (
    PreconditionError,
    assert_request_lineage_unchanged,
    check_runtime_metrics,
    infer_current_environment,
)
from .protocol import (
    PromotionApprovalRecord,
    PromotionRequest,
    PromotionRunRecord,
    PromotionStageRecord,
    RollbackRecord,
)
from .rollback import execute_rollback
from .writers import PromotionWriter


class PromotionError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrategyPromotionService:
    """Validation PASSED → 环境晋升管线。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        strategy_registry: Any | None = None,
        candidate_service: Any | None = None,
        validation_service: Any | None = None,
        governance: Any | None = None,
        writer: PromotionWriter | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._strategy_registry = strategy_registry
        self._candidate_service = candidate_service
        self._validation_service = validation_service
        self._governance = governance
        self._writer = writer or PromotionWriter(registry)
        self._lock = PromotionLock(registry)
        self._requests: dict[str, PromotionRequest] = {}
        self._runs: dict[str, PromotionRunRecord] = {}

    def _load_request(self, request_id: str) -> PromotionRequest:
        rid = str(request_id).strip()
        if rid in self._requests:
            return self._requests[rid]
        row = self._registry.get_strategy_promotion_request(rid)
        from .protocol import PromotionApprovalRecord as Appr

        req = PromotionRequest(
            request_id=row.request_id,
            pipeline_run_id=row.pipeline_run_id,
            idempotency_key=row.idempotency_key,
            strategy_code=row.strategy_code,
            candidate_id=row.candidate_id,
            validation_id=row.validation_id,
            strategy_version=row.strategy_version,
            version_id=row.version_id,
            content_hash=row.content_hash,
            from_environment=row.from_environment,  # type: ignore[arg-type]
            to_environment=row.to_environment,  # type: ignore[arg-type]
            policy_id=row.policy_id,
            policy_version=row.policy_version,
            policy_content_hash=row.policy_content_hash,
            status=row.status,  # type: ignore[arg-type]
            operator=row.operator or "",
            approvals=[Appr.model_validate(a) for a in (row.approvals_json or [])],
            created_at=row.created_at or "",
            updated_at=row.updated_at or "",
        )
        self._requests[rid] = req
        return req

    def _load_run(self, pipeline_run_id: str) -> PromotionRunRecord:
        pid = str(pipeline_run_id).strip()
        if pid in self._runs:
            return self._runs[pid]
        row = self._registry.get_strategy_promotion_run(pid)
        from .protocol import PromotionStageRecord as Stage

        run = PromotionRunRecord(
            pipeline_run_id=row.pipeline_run_id,
            request_id=row.request_id,
            strategy_code=row.strategy_code,
            from_environment=row.from_environment,  # type: ignore[arg-type]
            to_environment=row.to_environment,  # type: ignore[arg-type]
            policy_id=row.policy_id,
            policy_version=row.policy_version,
            policy_content_hash=row.policy_content_hash,
            status=row.status,  # type: ignore[arg-type]
            stages=[Stage.model_validate(s) for s in (row.stages_json or [])],
            session_id=row.session_id or "",
            governance_state=row.governance_state or "",
            started_at=row.started_at or "",
            completed_at=row.completed_at or "",
            operator=row.operator or "",
            storage_uri=row.storage_uri or "",
        )
        self._runs[pid] = run
        return run

    def _find_request_by_idempotency(
        self, strategy_code: str, idempotency_key: str
    ) -> PromotionRequest | None:
        try:
            rows = self._registry.list_strategy_promotion_requests(strategy_code=strategy_code)
        except Exception:
            return None
        for row in rows:
            if str(row.idempotency_key) == idempotency_key:
                return self._load_request(row.request_id)
        return None

    def submit_request(
        self,
        *,
        strategy_code: str,
        candidate_id: str,
        validation_id: str,
        strategy_version: str,
        to_environment: str,
        idempotency_key: str,
        operator: str = "",
        from_environment: str | None = None,
    ) -> PromotionRequest:
        """创建晋升请求（钉死 validation + policy）。"""
        if self._strategy_registry is None:
            raise PromotionError("strategy_registry required")
        ikey = normalize_idempotency_key(idempotency_key)
        existing = self._find_request_by_idempotency(strategy_code, ikey)
        if existing is not None:
            return existing

        try:
            ctx = load_promotion_context(
                self._registry,
                candidate_id=candidate_id,
                validation_id=validation_id,
                strategy_version=strategy_version,
                candidate_service=self._candidate_service,
                strategy_registry=self._strategy_registry,
            )
        except (PreconditionError, BridgeFromCandidateError) as exc:
            raise PromotionError(str(exc)) from exc
        from_env = from_environment or infer_current_environment(
            self._registry, strategy_code=strategy_code, governance=self._governance
        )
        to_env = str(to_environment).upper()
        try:
            assert_environment_transition(from_env, to_env)  # type: ignore[arg-type]
        except InvalidPromotionTransitionError as exc:
            raise PromotionError(str(exc)) from exc
        policy = resolve_policy_for_transition(
            self._registry, from_env, to_env
        )
        pipeline_run_id = build_pipeline_run_id(
            strategy_code=strategy_code,
            idempotency_key=ikey,
            validation_id=validation_id,
            to_environment=to_env,
        )
        request_id = build_request_id(pipeline_run_id=pipeline_run_id)
        ts = _now()
        req = PromotionRequest(
            request_id=request_id,
            pipeline_run_id=pipeline_run_id,
            idempotency_key=ikey,
            strategy_code=strategy_code,
            candidate_id=candidate_id,
            validation_id=validation_id,
            strategy_version=strategy_version,
            version_id=ctx.version_id,
            content_hash=ctx.content_hash,
            from_environment=from_env,  # type: ignore[arg-type]
            to_environment=to_env,  # type: ignore[arg-type]
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_content_hash=policy.policy_content_hash,
            status="PENDING",
            operator=operator,
            created_at=ts,
            updated_at=ts,
        )
        saved = self._writer.write_request(req)
        self._requests[saved.request_id] = saved
        return saved

    def approve(
        self,
        request_id: str,
        operator: str,
        token: str = "",
        *,
        kind: str = "STRATEGY_GO_LIVE",
    ) -> PromotionRequest:
        """人工审批（LIVE / 需 approval 的 CL）。"""
        req = self._load_request(request_id)
        appr = PromotionApprovalRecord(
            kind=kind,
            operator=operator,
            approved_at=_now(),
            token_hash=hash_approval_token(token),
        )
        updated = req.model_copy(
            update={
                "approvals": [*req.approvals, appr],
                "status": "APPROVED",
                "updated_at": _now(),
            }
        )
        saved = self._writer.write_request(updated)
        self._requests[saved.request_id] = saved
        return saved

    def execute(
        self,
        request_id: str,
        *,
        inject: Mapping[str, Any] | None = None,
        operator: str = "",
    ) -> PromotionRunRecord:
        """幂等执行晋升管线。"""
        req = self._load_request(request_id)
        try:
            existing = self._load_run(req.pipeline_run_id)
            if existing.status == "COMPLETED":
                return existing
        except Exception:
            existing = None

        if self._strategy_registry is None:
            raise PromotionError("strategy_registry required")

        policy = resolve_policy_for_transition(
            self._registry,
            req.from_environment,
            req.to_environment,
            policy_id=req.policy_id,
            policy_version=req.policy_version,
        )
        if policy.policy_content_hash != req.policy_content_hash:
            raise PromotionError("policy pin mismatch")

        ctx = load_promotion_context(
            self._registry,
            candidate_id=req.candidate_id,
            validation_id=req.validation_id,
            strategy_version=req.strategy_version,
            candidate_service=self._candidate_service,
            strategy_registry=self._strategy_registry,
        )
        assert_request_lineage_unchanged(
            req,
            candidate_content_hash=ctx.content_hash,
            registry_content_hash=ctx.registry_content_hash,
        )
        check_runtime_metrics(
            policy.rules,
            to_environment=req.to_environment,
            inject=inject,
        )

        if req.to_environment == "LIVE":
            if policy.rules.required_approval and not req.approvals:
                raise PromotionError("LIVE promotion requires approval")
            if req.status not in ("APPROVED", "COMPLETED"):
                raise PromotionError("LIVE promotion requires approved request")

        try:
            self._lock.acquire(req.strategy_code, pipeline_run_id=req.pipeline_run_id)
        except PromotionLockError as exc:
            raise PromotionError(str(exc)) from exc

        started = _now()
        stages: list[PromotionStageRecord] = []
        session_id = ""
        gov_state = ""

        def _stage(name: str, **detail: Any) -> None:
            stages.append(
                PromotionStageRecord(
                    stage=name,  # type: ignore[arg-type]
                    status="OK",
                    detail=dict(detail),
                    at=_now(),
                )
            )

        run = PromotionRunRecord(
            pipeline_run_id=req.pipeline_run_id,
            request_id=req.request_id,
            strategy_code=req.strategy_code,
            from_environment=req.from_environment,
            to_environment=req.to_environment,
            policy_id=req.policy_id,
            policy_version=req.policy_version,
            policy_content_hash=req.policy_content_hash,
            status="IN_PROGRESS",
            stages=stages,
            started_at=started,
            operator=operator or req.operator,
        )
        self._writer.write_run(run)

        try:
            for stage_name in stages_for_transition(
                req.from_environment, req.to_environment
            ):
                if stage_name == "ELIGIBLE_CHECK":
                    _stage(stage_name, validation_id=req.validation_id)
                elif stage_name == "REGISTRY_BIND":
                    bind = bind_registry_version(
                        self._registry,
                        ctx,
                        strategy_registry=self._strategy_registry,
                    )
                    _stage(stage_name, **bind)
                elif stage_name in ("GOV_SHADOW", "GOV_CONTROLLED_LIVE", "GOV_LIVE"):
                    gov_target = {
                        "GOV_SHADOW": "SHADOW",
                        "GOV_CONTROLLED_LIVE": "CONTROLLED_LIVE",
                        "GOV_LIVE": "LIVE",
                    }[stage_name]
                    live_ok = gov_target == "LIVE" and bool(req.approvals)
                    if gov_target == "LIVE" and not live_ok:
                        raise PromotionError("LIVE requires STRATEGY_GO_LIVE approval")
                    gov_state = apply_governance_for_target(
                        self._governance,
                        strategy_code=req.strategy_code,
                        strategy_version=req.strategy_version,
                        to_environment=gov_target,
                        live_go_live_approved=live_ok,
                    )
                    _stage(stage_name, governance_state=gov_state)
                elif stage_name == "SHADOW_SESSION":
                    session_id = open_shadow_session(
                        strategy_code=req.strategy_code,
                        strategy_version=req.strategy_version,
                    )
                    _stage(stage_name, session_id=session_id)
                elif stage_name == "CL_SESSION":
                    session_id = open_controlled_live_session(
                        strategy_code=req.strategy_code,
                        strategy_version=req.strategy_version,
                    )
                    _stage(stage_name, session_id=session_id)
                elif stage_name == "LIVE_ELIGIBLE":
                    _stage(stage_name, eligible=True, direct_to_live=False)

            completed = run.model_copy(
                update={
                    "stages": stages,
                    "session_id": session_id,
                    "governance_state": gov_state,
                    "status": "COMPLETED",
                    "completed_at": _now(),
                }
            )
            saved = self._writer.write_run(completed)
            self._runs[saved.pipeline_run_id] = saved

            req_done = req.model_copy(update={"status": "COMPLETED", "updated_at": _now()})
            self._writer.write_request(req_done)
            self._requests[req.request_id] = req_done

            self._patch_candidate_metadata(req.candidate_id, saved.pipeline_run_id)
            return saved
        except (PreconditionError, PromotionError, PromotionLockError) as exc:
            failed = run.model_copy(
                update={
                    "stages": stages,
                    "status": "FAILED",
                    "completed_at": _now(),
                }
            )
            self._writer.write_run(failed)
            raise PromotionError(str(exc)) from exc

    def _patch_candidate_metadata(self, candidate_id: str, pipeline_run_id: str) -> None:
        if self._candidate_service is None:
            return
        try:
            cand = self._candidate_service.get(candidate_id)
            meta = dict(getattr(cand, "metadata", None) or {})
            meta["last_promotion_run_id"] = pipeline_run_id
            updated = cand.model_copy(update={"metadata": meta})
            from app.services.strategy_candidate.writers import StrategyCandidateWriter

            StrategyCandidateWriter(self._registry).write_candidate(updated)
            if hasattr(self._candidate_service, "_candidates"):
                self._candidate_service._candidates[candidate_id] = updated
        except Exception:
            pass

    def rollback(
        self,
        strategy_code: str,
        to_version: str,
        *,
        reason: str,
        operator: str,
    ) -> RollbackRecord:
        rec = execute_rollback(
            strategy_code=strategy_code,
            to_version=to_version,
            reason=reason,
            operator=operator,
            governance=self._governance,
        )
        return self._writer.write_rollback(rec)

    def get_run(self, pipeline_run_id: str) -> PromotionRunRecord:
        return self._load_run(pipeline_run_id)

    def list_runs(self, strategy_code: str) -> list[PromotionRunRecord]:
        rows = self._registry.list_strategy_promotion_runs(strategy_code=strategy_code)
        out = []
        for row in rows:
            out.append(self._load_run(row.pipeline_run_id))
        out.sort(key=lambda r: r.completed_at or r.started_at or "")
        return out

    def get_request(self, request_id: str) -> PromotionRequest:
        return self._load_request(request_id)


__all__ = ["PromotionError", "StrategyPromotionService"]
