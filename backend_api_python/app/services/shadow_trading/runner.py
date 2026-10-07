"""Phase 7B：ShadowTradingService（无 submit_real / cancel_real）。"""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.services.research_data.contracts import OrderIntent
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ShadowArtifactStore
from .compare import compare_positions
from .gateway import OrderExecutionGateway
from .ledger import ShadowLedger
from .modes import normalize_environment
from .oms import ShadowOMS, ShadowOmsError
from .protocol import ShadowCompareReport, ShadowSession
from .session import open_shadow_session
from .simulator import QuoteLike, ShadowExecutionSimulator, SimulatorConfig
from .writers import ShadowWriter


class ShadowTradingError(RuntimeError):
    pass


class ShadowTradingService:
    """Shadow 编排：Intent → OMS → Simulator → Ledger；永不触达真实 Broker。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        md: Any | None = None,
        risk: Callable[[OrderIntent], tuple[bool, str]] | None = None,
        live_readonly: Any | None = None,
        ops: Any | None = None,
        artifact_store: ShadowArtifactStore | None = None,
        simulator: ShadowExecutionSimulator | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._md = md
        self._risk = risk or (lambda _i: (True, "DEFAULT_ALLOW"))
        self._live_readonly = live_readonly
        self._ops = ops
        self._writer = ShadowWriter(registry, artifact_store=artifact_store)
        self._oms = ShadowOMS()
        self._ledger = ShadowLedger()
        self._sim = simulator or ShadowExecutionSimulator()
        self._gateway = OrderExecutionGateway()
        self._session: ShadowSession | None = None
        self._environment = "SHADOW"

    @property
    def gateway(self) -> OrderExecutionGateway:
        return self._gateway

    def assert_environment(self, expected: str) -> str:
        env = normalize_environment(expected)
        if self._environment != env:
            raise ShadowTradingError(
                f"environment mismatch: current={self._environment!r}, expected={env!r}"
            )
        return env

    def start_session(
        self,
        *,
        account_id: str,
        dataset_hash: str,
        model_version: str,
        strategy_version: str,
    ) -> ShadowSession:
        session = open_shadow_session(
            account_id=account_id,
            dataset_hash=dataset_hash,
            model_version=model_version,
            strategy_version=strategy_version,
        )
        self._writer.write_session(session)
        self._session = session
        self._environment = "SHADOW"
        return session

    def submit_intent(self, intent: OrderIntent, *, strategy_id: str = "") -> Any:
        """必经 Risk；只写 Shadow OMS。"""
        if self._session is None:
            raise ShadowTradingError("no shadow session")
        approved, decision = self._risk(intent)
        if not approved:
            raise ShadowOmsError(f"risk rejected: {decision}")
        order = self._oms.submit_intent(
            intent,
            session=self._session,
            strategy_id=strategy_id,
            risk_approved=approved,
            risk_decision=decision,
        )
        self._writer.write_order_index(order, session_id=self._session.session_id)
        return order

    def simulate_fills_for_symbol(self, symbol: str, *, bid: float, ask: float) -> list[Any]:
        """对某 symbol 的 open orders 尝试模拟成交。"""
        quote = QuoteLike(bid=bid, ask=ask)
        execs = []
        for order in self._oms.list_orders():
            if order.symbol.upper() != symbol.upper():
                continue
            if order.status in ("FILLED", "CANCELLED", "REJECTED", "EXPIRED"):
                continue
            updated, execution = self._sim.try_fill(order, quote)
            self._oms.update_order(updated)
            self._writer.write_order_index(updated, session_id=self._session.session_id if self._session else "")
            if execution:
                self._ledger.apply_execution(execution)
                self._writer.write_execution_index(
                    execution, session_id=self._session.session_id if self._session else ""
                )
                execs.append(execution)
        return execs

    def run_cycle(
        self,
        intents: list[OrderIntent],
        *,
        marks: dict[str, float] | None = None,
        strategy_id: str = "",
    ) -> dict[str, Any]:
        """MD hook（可选）→ intents → risk → shadow oms → sim。"""
        orders = [self.submit_intent(i, strategy_id=strategy_id) for i in intents]
        if marks:
            for sym, mid in marks.items():
                self.simulate_fills_for_symbol(sym, bid=mid * 0.999, ask=mid * 1.001)
        return {"orders": orders, "equity": self._ledger.equity(marks or {})}

    def get_shadow_positions(self) -> dict[str, Any]:
        return {k: v.model_dump() for k, v in self._ledger.positions.items()}

    def get_shadow_pnl(self) -> dict[str, float]:
        return {"realized_pnl": self._ledger.realized_pnl, "cash": self._ledger.cash}

    def compare_with_live(self, account_id: str) -> ShadowCompareReport:
        if self._live_readonly is None:
            raise ShadowTradingError("live_readonly adapter not configured")
        live_pos = self._live_readonly.get_positions()
        report = compare_positions(
            account_id=account_id,
            shadow_positions=self._ledger.positions,
            live_positions=live_pos,
        )
        self._writer.write_compare_run(report)
        return report
