"""TradingGate：CRITICAL OPEN Finding → 阻断新 submit。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .protocol import GateState, ReconciliationFinding


class TradingGate:
    """账户级交易门：仅阻断新单；cancel/query/reconcile 不受限。"""

    def __init__(self, repository: Any = None) -> None:
        self._repo = repository
        self._mem: dict[str, GateState] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get(self, account_id: str) -> GateState:
        if self._repo is not None:
            try:
                return self._repo.get_gate(account_id)
            except KeyError:
                pass
        return self._mem.get(account_id) or GateState(account_id=account_id)

    def is_blocked(self, account_id: str) -> bool:
        return bool(self.get(account_id).blocked)

    def apply_findings(
        self,
        account_id: str,
        findings: list[ReconciliationFinding],
    ) -> GateState:
        """任一 CRITICAL+OPEN → block；否则保持现状（clear 需显式调用）。"""
        critical = [
            f
            for f in findings
            if str(f.severity).upper() == "CRITICAL"
            and str(f.status).upper() == "OPEN"
        ]
        if not critical:
            return self.get(account_id)
        top = critical[0]
        state = GateState(
            account_id=account_id,
            blocked=True,
            reason=f"CRITICAL:{top.type}:{top.entity_id}",
            finding_id=top.finding_id,
            updated_at=self._now(),
        )
        self._persist(state)
        return state

    def clear(self, account_id: str, *, reason: str = "cleared") -> GateState:
        state = GateState(
            account_id=account_id,
            blocked=False,
            reason=reason,
            finding_id="",
            updated_at=self._now(),
        )
        self._persist(state)
        return state

    def set_blocked(
        self,
        account_id: str,
        *,
        blocked: bool,
        reason: str = "",
        finding_id: str = "",
    ) -> GateState:
        state = GateState(
            account_id=account_id,
            blocked=blocked,
            reason=reason,
            finding_id=finding_id,
            updated_at=self._now(),
        )
        self._persist(state)
        return state

    def _persist(self, state: GateState) -> None:
        self._mem[state.account_id] = state
        if self._repo is not None:
            self._repo.set_gate(state)
