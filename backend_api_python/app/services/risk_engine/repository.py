"""Risk Repository 协议。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import (
    RiskDecisionEventRecord,
    RiskPolicySummary,
    RiskRunSummary,
)


class RiskRepository(Protocol):
    def upsert_risk_policy(self, record: RiskPolicySummary) -> None: ...

    def get_risk_policy(
        self, policy_code: str, policy_version: str
    ) -> RiskPolicySummary: ...

    def get_risk_policy_by_hash(self, policy_hash: str) -> RiskPolicySummary: ...

    def upsert_risk_run(self, record: RiskRunSummary) -> None: ...

    def get_risk_run_by_idempotency(self, idempotency_key: str) -> RiskRunSummary: ...

    def get_risk_run(self, risk_run_id: str) -> RiskRunSummary: ...

    def append_risk_decision_event(
        self, record: RiskDecisionEventRecord
    ) -> None: ...
