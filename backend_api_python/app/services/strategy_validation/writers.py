"""Phase 8C：ValidationRun / Policy → D1 + R2。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ValidationArtifactStore
from .protocol import (
    ENGINE_VERSION,
    ValidationPolicyRecord,
    ValidationResult,
    ValidationRunRecord,
)


class ValidationWriter:
    """索引与 result 写入；Run 完成后不可变。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: ValidationArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or ValidationArtifactStore()

    def write_policy(self, policy: ValidationPolicyRecord) -> None:
        from app.services.research_data.contracts import StrategyValidationPolicySummary

        self._registry.upsert_strategy_validation_policy(
            StrategyValidationPolicySummary(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                policy_content_hash=policy.policy_content_hash,
                rules_json=policy.rules.model_dump(mode="json"),
                engine_version=policy.engine_version or ENGINE_VERSION,
                description=policy.description,
            )
        )

    def write_run(
        self,
        run: ValidationRunRecord,
        result: ValidationResult,
    ) -> ValidationRunRecord:
        from app.services.research_data.contracts import StrategyValidationRunSummary

        uri, cs = self._artifacts.write_result(run, result)
        completed = run.model_copy(
            update={"storage_uri": uri, "result": result, "status": run.status}
        )
        self._registry.upsert_strategy_validation_run(
            StrategyValidationRunSummary(
                validation_id=completed.validation_id,
                candidate_id=completed.candidate_id,
                candidate_version=completed.candidate_version,
                dataset_hash=completed.dataset_hash,
                snapshot_id=completed.snapshot_id,
                policy_id=completed.policy_id,
                policy_version=completed.policy_version,
                policy_content_hash=completed.policy_content_hash,
                validator_version=completed.validator_version,
                started_at=completed.started_at,
                completed_at=completed.completed_at,
                status=completed.status,
                operator=completed.operator,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs},
            )
        )
        return completed


__all__ = ["ValidationWriter"]
