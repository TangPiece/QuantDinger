"""Risk Policy / Run / Event → Registry。"""

from __future__ import annotations

from app.services.research_data.contracts import (
    RiskDecisionEventRecord,
    RiskPolicySummary,
    RiskRunSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import RiskArtifactStore
from .protocol import ENGINE_VERSION, RiskEvaluateResult, RiskPolicy


class RiskWriter:
    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: RiskArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or RiskArtifactStore()

    def write_policy(self, policy: RiskPolicy) -> RiskPolicySummary:
        summary = RiskPolicySummary(
            policy_hash=policy.policy_hash,
            policy_code=policy.policy_code,
            policy_version=policy.policy_version,
            engine_version=policy.engine_version or ENGINE_VERSION,
            metadata={
                "max_single_position_weight": policy.max_single_position_weight,
                "max_gross_exposure": policy.max_gross_exposure,
                "max_turnover": policy.max_turnover,
                "max_position_delta_weight": policy.max_position_delta_weight,
                "clip_on_limit": policy.clip_on_limit,
                **dict(policy.metadata or {}),
            },
        )
        self._registry.upsert_risk_policy(summary)
        return summary

    def write_run(self, result: RiskEvaluateResult) -> RiskRunSummary:
        uri = self._artifacts.write_run(result)
        if result.snapshot is not None:
            result = result.model_copy(
                update={
                    "snapshot": result.snapshot.model_copy(
                        update={"storage_uri": uri}
                    )
                }
            )
        rec = RiskRunSummary(
            risk_run_id=result.risk_run_id,
            idempotency_key=result.idempotency_key,
            policy_hash=result.policy_hash,
            account_id=str((result.metadata or {}).get("account_id") or ""),
            portfolio_id=str((result.metadata or {}).get("portfolio_id") or ""),
            apply_id=str((result.metadata or {}).get("apply_id") or ""),
            trading_date=str((result.metadata or {}).get("trading_date") or ""),
            verdict=result.verdict,
            n_intents=len(result.order_intents),
            n_violations=len(result.violations),
            storage_uri=uri,
            metadata=dict(result.metadata or {}),
        )
        self._registry.upsert_risk_run(rec)
        for ev in result.events:
            self._registry.append_risk_decision_event(
                RiskDecisionEventRecord(
                    event_id=ev.event_id,
                    risk_run_id=ev.risk_run_id,
                    rule_code=ev.rule_code,
                    decision=str(ev.decision),
                    severity=ev.severity,
                    instrument_key=ev.instrument_key,
                    message=ev.message,
                    original_value=float(ev.original_value),
                    limit_value=float(ev.limit_value),
                    payload_json=dict(ev.payload or {}),
                    created_at=ev.created_at,
                )
            )
        return rec
