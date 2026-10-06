"""ReconciliationService：观察者编排；CRITICAL Gate 阻断新单。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ReconciliationArtifactStore
from .cursor import CursorStore
from .cycle import run_reconciliation
from .findings import (
    acknowledge,
    investigate,
    resolve,
    waive,
)
from .gate import TradingGate
from .protocol import ReconciliationFinding, ReconciliationRun, RunMode
from .writers import ReconciliationWriter


class ReconciliationError(RuntimeError):
    """对账服务错误。"""


class ReconciliationService:
    """6F 主入口：run / findings lifecycle / trading gate。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        portfolio_service: Any = None,
        oms_service: Any = None,
        broker_adapter_service: Any = None,
        broker_adapter: Any = None,
        artifact_store: ReconciliationArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._portfolio = portfolio_service
        self._oms = oms_service
        self._broker_svc = broker_adapter_service
        self._adapter = broker_adapter
        self._writer = ReconciliationWriter(registry, artifact_store=artifact_store)
        self._gate = TradingGate(repository=self._writer)
        self._cursors = CursorStore(repository=self._writer)

    def _resolve_adapter(self) -> Any:
        if self._adapter is not None:
            return self._adapter
        if self._broker_svc is not None:
            ad = getattr(self._broker_svc, "_adapter", None) or getattr(
                self._broker_svc, "adapter", None
            )
            if ad is not None:
                return ad
        raise ReconciliationError("no broker adapter configured")

    def run(
        self,
        account_id: str,
        portfolio_id: str,
        *,
        mode: RunMode | str = "FAST",
        inject: Mapping[str, Any] | None = None,
        salt: str = "",
    ) -> ReconciliationRun:
        """FAST | SLOW | EOD 对账。"""
        m = str(mode).upper()
        if m not in ("FAST", "SLOW", "EOD"):
            raise ReconciliationError(f"invalid mode: {mode!r}")
        if self._portfolio is None or self._oms is None:
            raise ReconciliationError("portfolio_service and oms_service required")
        adapter = self._resolve_adapter()
        run, _ = run_reconciliation(
            account_id=account_id,
            portfolio_id=portfolio_id,
            mode=m,  # type: ignore[arg-type]
            writer=self._writer,
            gate=self._gate,
            cursor_store=self._cursors,
            portfolio_service=self._portfolio,
            oms_service=self._oms,
            broker_adapter=adapter,
            inject=inject,
            salt=salt,
        )
        return run

    def list_findings(
        self,
        *,
        run_id: str | None = None,
        account_id: str | None = None,
        status: str | None = None,
    ) -> list[ReconciliationFinding]:
        return self._writer.list_findings(
            run_id=run_id or "",
            account_id=account_id or "",
            status=status or "",
        )

    def acknowledge(self, finding_id: str, *, note: str = "") -> ReconciliationFinding:
        f = self._writer.get_finding(finding_id)
        updated = acknowledge(f, note=note)
        self._writer.write_finding(updated)
        return updated

    def investigate(self, finding_id: str, *, note: str = "") -> ReconciliationFinding:
        f = self._writer.get_finding(finding_id)
        updated = investigate(f, note=note)
        self._writer.write_finding(updated)
        return updated

    def resolve(self, finding_id: str, *, note: str = "") -> ReconciliationFinding:
        f = self._writer.get_finding(finding_id)
        updated = resolve(f, note=note)
        self._writer.write_finding(updated)
        account_id = str((updated.metadata or {}).get("account_id") or "")
        if account_id:
            self._maybe_clear_gate(account_id)
        return updated

    def waive(self, finding_id: str, *, note: str = "") -> ReconciliationFinding:
        """CRITICAL 抛 FindingsError。"""
        f = self._writer.get_finding(finding_id)
        updated = waive(f, note=note)
        self._writer.write_finding(updated)
        return updated

    def _maybe_clear_gate(self, account_id: str) -> None:
        if not account_id:
            return
        crit = [
            f
            for f in self._writer.list_findings(account_id=account_id)
            if str(f.severity).upper() == "CRITICAL"
            and str(f.status).upper() == "OPEN"
        ]
        if crit:
            return
        self._gate.clear(account_id, reason="no open CRITICAL")
        if self._portfolio is not None:
            try:
                from app.services.portfolio_service.state_machine import assert_transition

                acct = self._portfolio.get_account(account_id)
                if str(acct.status) == "RECONCILIATION_REQUIRED":
                    assert_transition(acct.status, "ACTIVE")
                    restored = acct.model_copy(update={"status": "ACTIVE"})
                    w = getattr(self._portfolio, "_writer", None)
                    if w is not None:
                        w.write_account(restored)
            except Exception:
                pass

    def refresh_and_retry(
        self, account_id: str, portfolio_id: str, *, salt: str = ""
    ) -> ReconciliationRun:
        """仅 refresh snapshot + re-run（不下单）。"""
        return self.run(
            account_id, portfolio_id, mode="SLOW", salt=salt or "retry"
        )

    def is_trading_blocked(self, account_id: str) -> bool:
        return self._gate.is_blocked(account_id)

    @property
    def gate(self) -> TradingGate:
        return self._gate
