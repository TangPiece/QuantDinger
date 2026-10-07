"""Phase 8B：StrategyCandidateService 门面（无 Shadow/LIVE/8C Gate/OMS）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .bridge_from_research import build_candidate_from_research
from .pin import assert_lineage_compatible
from .promotion import promotion_for_registry, promotion_for_state_change
from .protocol import PromotionRecord, StrategyCandidateRecord
from .state_machine import InvalidTransitionError, assert_transition, target_for_action
from .writers import StrategyCandidateWriter


class CandidateError(RuntimeError):
    pass


class LineageImmutableError(RuntimeError):
    """lineage 冻结后禁止修改钉扎字段。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrategyCandidateService:
    """Research → StrategyCandidate；可选 promote 至 8A Registry。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        strategy_registry: Any | None = None,
        writer: StrategyCandidateWriter | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._strategy_registry = strategy_registry
        self._writer = writer or StrategyCandidateWriter(registry)
        self._candidates: dict[str, StrategyCandidateRecord] = {}
        self._promotions: dict[str, list[PromotionRecord]] = {}

    def _get_or_load(self, candidate_id: str) -> StrategyCandidateRecord:
        cid = str(candidate_id).strip()
        if cid in self._candidates:
            return self._candidates[cid]
        try:
            row = self._registry.get_strategy_candidate(cid)
        except Exception as exc:
            raise CandidateError(f"candidate not found: {cid}") from exc
        rec = self._summary_to_record(row)
        self._candidates[cid] = rec
        return rec

    @staticmethod
    def _summary_to_record(row: Any) -> StrategyCandidateRecord:
        meta = dict(row.metadata or {})
        frozen = bool(meta.get("lineage_frozen"))
        return StrategyCandidateRecord(
            candidate_id=row.candidate_id,
            strategy_code=row.strategy_code,
            candidate_version=row.candidate_version,
            experiment_id=row.experiment_id,
            backtest_hash=row.backtest_hash,
            model_version=row.model_version,
            model_artifact_id=row.model_artifact_id,
            dataset_hash=row.dataset_hash,
            snapshot_id=row.snapshot_id,
            feature_version=row.feature_version,
            processor_version=row.processor_version,
            processor_hash=row.processor_hash,
            strategy_hash=row.strategy_hash,
            strategy_definition_json=dict(row.strategy_definition_json or {}),
            risk_policy_ref=row.risk_policy_ref,
            execution_policy_ref=row.execution_policy_ref,
            evaluation_hash=row.evaluation_hash,
            cv_hash=row.cv_hash,
            content_hash=row.content_hash,
            source=row.source,  # type: ignore[arg-type]
            status=row.status,  # type: ignore[arg-type]
            lineage_frozen_at=row.lineage_frozen_at or "",
            created_at=row.created_at or "",
            storage_uri=row.storage_uri or "",
            lineage_frozen=frozen,
            metadata={k: v for k, v in meta.items() if k not in ("checksum", "lineage_frozen")},
        )

    def _persist(self, record: StrategyCandidateRecord) -> StrategyCandidateRecord:
        saved = self._writer.write_candidate(record)
        self._candidates[saved.candidate_id] = saved
        return saved

    def _transition(
        self,
        candidate_id: str,
        action: str,
        *,
        operator: str = "",
        reason: str = "",
        write_promotion: bool = True,
    ) -> StrategyCandidateRecord:
        rec = self._get_or_load(candidate_id)
        to_status = target_for_action(action)  # type: ignore[arg-type]
        try:
            assert_transition(rec.status, to_status)
        except InvalidTransitionError as exc:
            raise CandidateError(str(exc)) from exc
        from_status = rec.status
        updated = rec.model_copy(update={"status": to_status})
        saved = self._persist(updated)
        if write_promotion and action in ("generate", "mark_validated"):
            prom = promotion_for_state_change(
                saved,
                from_state=from_status,
                to_state="GENERATED" if action == "generate" else "VALIDATED",
                operator=operator,
                reason=reason,
            )
            self._writer.write_promotion(prom)
            self._promotions.setdefault(saved.candidate_id, []).append(prom)
        return saved

    def create_from_research(
        self,
        strategy_code: str,
        *,
        candidate_version: str,
        experiment_id: str = "",
        backtest_hash: str = "",
        strategy_hash: str = "",
        evaluation_hash: str = "",
        cv_hash: str = "",
        risk_policy_ref: str = "",
        execution_policy_ref: str = "NEXT_OPEN",
        metadata: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> StrategyCandidateRecord:
        """从研究证据创建 DRAFT；同 content_hash 幂等。"""
        draft = build_candidate_from_research(
            self._registry,
            strategy_code=strategy_code,
            candidate_version=candidate_version,
            experiment_id=experiment_id,
            backtest_hash=backtest_hash,
            strategy_hash=strategy_hash,
            evaluation_hash=evaluation_hash,
            cv_hash=cv_hash,
            risk_policy_ref=risk_policy_ref,
            execution_policy_ref=execution_policy_ref,
            metadata=metadata,
            created_at=_now(),
            **kwargs,
        )
        for existing in self.list(draft.strategy_code):
            if existing.candidate_version != draft.candidate_version:
                continue
            if existing.content_hash == draft.content_hash:
                return existing
            try:
                assert_lineage_compatible(
                    existing.model_dump(mode="json"),
                    draft.model_dump(mode="json"),
                )
            except ValueError as exc:
                raise LineageImmutableError(str(exc)) from exc
            return existing
        existing_id = draft.candidate_id
        if existing_id in self._candidates or self._registry_has_candidate(existing_id):
            existing = self._get_or_load(existing_id)
            try:
                assert_lineage_compatible(
                    existing.model_dump(mode="json"),
                    draft.model_dump(mode="json"),
                )
            except ValueError as exc:
                raise LineageImmutableError(str(exc)) from exc
            return existing
        return self._persist(draft)

    def _registry_has_candidate(self, candidate_id: str) -> bool:
        try:
            self._registry.get_strategy_candidate(candidate_id)
            return True
        except Exception:
            return False

    def generate(
        self,
        candidate_id: str,
        *,
        operator: str = "",
        reason: str = "",
    ) -> StrategyCandidateRecord:
        """DRAFT → GENERATED，冻结 lineage。"""
        rec = self._get_or_load(candidate_id)
        if rec.lineage_frozen and rec.status != "DRAFT":
            return rec
        frozen = rec.model_copy(
            update={
                "lineage_frozen": True,
                "lineage_frozen_at": _now(),
            }
        )
        self._candidates[frozen.candidate_id] = frozen
        return self._transition(
            candidate_id,
            "generate",
            operator=operator,
            reason=reason,
        )

    def start_evaluating(self, candidate_id: str) -> StrategyCandidateRecord:
        return self._transition(candidate_id, "start_evaluating", write_promotion=False)

    def mark_ready(self, candidate_id: str) -> StrategyCandidateRecord:
        return self._transition(candidate_id, "mark_ready", write_promotion=False)

    def mark_validated(
        self,
        candidate_id: str,
        *,
        operator: str = "",
        reason: str = "",
    ) -> StrategyCandidateRecord:
        """READY_FOR_VALIDATION → VALIDATED（非 8C Gate PASSED）。"""
        return self._transition(
            candidate_id,
            "mark_validated",
            operator=operator,
            reason=reason,
        )

    def reject(self, candidate_id: str, *, reason: str = "") -> StrategyCandidateRecord:
        return self._transition(candidate_id, "reject", reason=reason, write_promotion=False)

    def expire(self, candidate_id: str, *, reason: str = "") -> StrategyCandidateRecord:
        return self._transition(candidate_id, "expire", reason=reason, write_promotion=False)

    def promote_to_registry(
        self,
        candidate_id: str,
        *,
        target_strategy_version: str,
        operator: str = "",
        reason: str = "",
        require_gate_passed: bool = True,
    ) -> tuple[StrategyCandidateRecord, PromotionRecord, Any]:
        """仅 VALIDATED → 8A register_version_manual；默认须 8C ValidationRun PASSED。"""
        if self._strategy_registry is None:
            raise CandidateError("strategy_registry required for promote_to_registry")
        rec = self._get_or_load(candidate_id)
        if rec.status != "VALIDATED":
            raise CandidateError("promote_to_registry requires VALIDATED status")
        if require_gate_passed:
            runs = self._registry.list_strategy_validation_runs(candidate_id=rec.candidate_id)
            latest = str(runs[-1].status or "") if runs else ""
            if latest != "PASSED":
                raise CandidateError(
                    "promote_to_registry requires latest ValidationRun.status=PASSED"
                )
        label = str(target_strategy_version).strip()
        if not label:
            raise CandidateError("target_strategy_version required")
        ver = self._strategy_registry.register_version_manual(
            rec.strategy_code,
            label,
            dataset_hash=rec.dataset_hash,
            snapshot_id=rec.snapshot_id,
            model_version=rec.model_version,
            model_artifact_id=rec.model_artifact_id,
            feature_version=rec.feature_version,
            processor_version=rec.processor_version,
            processor_hash=rec.processor_hash,
            strategy_hash=rec.strategy_hash,
            risk_policy_ref=rec.risk_policy_ref,
            execution_policy_ref=rec.execution_policy_ref,
            source="RESEARCH",
            metadata={"candidate_id": rec.candidate_id, "content_hash": rec.content_hash},
        )
        prom = promotion_for_registry(
            rec,
            target_strategy_version=label,
            version_id=ver.version_id,
            operator=operator,
            reason=reason,
        )
        self._writer.write_promotion(prom)
        self._promotions.setdefault(rec.candidate_id, []).append(prom)
        return rec, prom, ver

    def get(self, candidate_id: str) -> StrategyCandidateRecord:
        return self._get_or_load(candidate_id)

    def list(self, strategy_code: str | None = None) -> list[StrategyCandidateRecord]:
        rows = self._registry.list_strategy_candidates(strategy_code=strategy_code)
        out = [self._summary_to_record(r) for r in rows]
        for rec in out:
            self._candidates[rec.candidate_id] = rec
        out.sort(key=lambda r: r.created_at or "")
        return out

    def get_promotions(self, candidate_id: str) -> list[PromotionRecord]:
        cid = str(candidate_id).strip()
        if cid in self._promotions:
            return list(self._promotions[cid])
        rows = self._registry.list_strategy_candidate_promotions(candidate_id=cid)
        out = [
            PromotionRecord(
                promotion_id=r.promotion_id,
                candidate_id=r.candidate_id,
                source_type=r.source_type,  # type: ignore[arg-type]
                source_id=r.source_id,
                target_strategy_code=r.target_strategy_code,
                target_strategy_version=r.target_strategy_version,
                version_id=r.version_id,
                from_state=r.from_state,
                to_state=r.to_state,  # type: ignore[arg-type]
                dataset_hash=r.dataset_hash,
                model_version=r.model_version,
                operator=r.operator,
                reason=r.reason,
                status=r.status,  # type: ignore[arg-type]
                created_at=r.created_at or "",
            )
            for r in rows
        ]
        self._promotions[cid] = out
        return out


__all__ = [
    "CandidateError",
    "LineageImmutableError",
    "StrategyCandidateService",
]
