"""Phase 8C：ValidationGateService 门面（无 Shadow/LIVE/OMS）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .bridge_from_candidate import build_evidence_context
from .identity import build_validation_id
from .policy import list_all_policies, resolve_policy
from .protocol import ValidationPolicyRecord, ValidationRunRecord
from .report import build_validation_result, run_status_from_result
from .writers import ValidationWriter


class ValidationGateError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ValidationGateService:
    """对 StrategyCandidate 做只读准入审查。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        candidate_service: Any | None = None,
        governance: Any | None = None,
        writer: ValidationWriter | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._candidate_service = candidate_service
        self._governance = governance
        self._writer = writer or ValidationWriter(registry)
        self._runs: dict[str, ValidationRunRecord] = {}

    def _load_candidate(self, candidate_id: str) -> Any:
        if self._candidate_service is not None:
            return self._candidate_service.get(candidate_id)
        from app.services.strategy_candidate.runner import StrategyCandidateService

        svc = StrategyCandidateService(self._store, self._registry)
        return svc.get(candidate_id)

    def _get_run_record(self, validation_id: str) -> ValidationRunRecord:
        vid = str(validation_id).strip()
        if vid in self._runs:
            return self._runs[vid]
        row = self._registry.get_strategy_validation_run(vid)
        rec = ValidationRunRecord(
            validation_id=row.validation_id,
            candidate_id=row.candidate_id,
            candidate_version=row.candidate_version,
            dataset_hash=row.dataset_hash,
            snapshot_id=row.snapshot_id,
            policy_id=row.policy_id,
            policy_version=row.policy_version,
            policy_content_hash=row.policy_content_hash,
            validator_version=row.validator_version,
            started_at=row.started_at or "",
            completed_at=row.completed_at or "",
            status=row.status,  # type: ignore[arg-type]
            operator=row.operator or "",
            storage_uri=row.storage_uri or "",
        )
        self._runs[vid] = rec
        return rec

    def _patch_candidate_gate_metadata(
        self,
        candidate: Any,
        *,
        validation_id: str,
        gate_status: str,
    ) -> None:
        """仅写 metadata.last_*，不改 lineage pin。"""
        meta = dict(getattr(candidate, "metadata", None) or {})
        meta["last_validation_run_id"] = validation_id
        meta["last_gate_status"] = gate_status
        updated = candidate.model_copy(update={"metadata": meta})
        from app.services.strategy_candidate.writers import StrategyCandidateWriter

        saved = StrategyCandidateWriter(self._registry).write_candidate(updated)
        if self._candidate_service is not None and hasattr(
            self._candidate_service, "_candidates"
        ):
            # 刷新 Candidate 内存缓存，避免 get() 读到旧 metadata
            self._candidate_service._candidates[saved.candidate_id] = saved

    def run(
        self,
        candidate_id: str,
        *,
        policy_id: str = "default_research_v1",
        policy_version: str | None = None,
        inject: Mapping[str, Any] | None = None,
        operator: str = "",
    ) -> ValidationRunRecord:
        """执行 Gate；同 candidate+policy 幂等返回已有 Run。"""
        cand = self._load_candidate(candidate_id)
        policy = resolve_policy(self._registry, policy_id, policy_version)
        if policy.rules.allow_recompute:
            raise ValidationGateError("allow_recompute not supported in 8C P0")

        validation_id = build_validation_id(
            candidate_id=cand.candidate_id,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_content_hash=policy.policy_content_hash,
        )
        try:
            existing = self._get_run_record(validation_id)
            if existing.completed_at and existing.status != "VALIDATING":
                return existing
        except Exception:
            pass

        ctx = build_evidence_context(self._registry, cand, inject=inject)
        result = build_validation_result(ctx, policy.rules)
        status = run_status_from_result(result)
        started = _now()
        run = ValidationRunRecord(
            validation_id=validation_id,
            candidate_id=cand.candidate_id,
            candidate_version=cand.candidate_version,
            dataset_hash=cand.dataset_hash,
            snapshot_id=cand.snapshot_id,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_content_hash=policy.policy_content_hash,
            started_at=started,
            completed_at=started,
            status=status,
            operator=operator,
        )
        saved = self._writer.write_run(run, result)
        self._runs[saved.validation_id] = saved
        self._patch_candidate_gate_metadata(
            cand,
            validation_id=saved.validation_id,
            gate_status=str(saved.status),
        )
        return saved

    def get_run(self, validation_id: str) -> ValidationRunRecord:
        return self._get_run_record(validation_id)

    def list_runs(self, candidate_id: str) -> list[ValidationRunRecord]:
        cid = str(candidate_id).strip()
        rows = self._registry.list_strategy_validation_runs(candidate_id=cid)
        out = [
            ValidationRunRecord(
                validation_id=r.validation_id,
                candidate_id=r.candidate_id,
                candidate_version=r.candidate_version,
                dataset_hash=r.dataset_hash,
                snapshot_id=r.snapshot_id,
                policy_id=r.policy_id,
                policy_version=r.policy_version,
                policy_content_hash=r.policy_content_hash,
                validator_version=r.validator_version,
                started_at=r.started_at or "",
                completed_at=r.completed_at or "",
                status=r.status,  # type: ignore[arg-type]
                operator=r.operator or "",
                storage_uri=r.storage_uri or "",
            )
            for r in rows
        ]
        for rec in out:
            self._runs[rec.validation_id] = rec
        out.sort(key=lambda r: r.completed_at or r.started_at or "")
        return out

    def latest_run_status(self, candidate_id: str) -> str | None:
        """最新 ValidationRun 的 status（promote 门禁用）。"""
        runs = self.list_runs(candidate_id)
        if not runs:
            return None
        return str(runs[-1].status or "")

    def get_policy(
        self,
        policy_id: str,
        version: str | None = None,
    ) -> ValidationPolicyRecord:
        return resolve_policy(self._registry, policy_id, version)

    def list_policies(self) -> list[ValidationPolicyRecord]:
        return list_all_policies(self._registry)


__all__ = ["ValidationGateError", "ValidationGateService"]
