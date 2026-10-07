"""Phase 7A：LiveReadonlyService 主入口（不接 OMS broker_port 发单）。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.reconciliation_service.protocol import BrokerSnapshot, ReconciliationRun
from app.services.research_data.registry import ResearchRegistry

from .adapter import LiveReadonlyAdapter, fake_adapter
from .artifact_store import LiveReadonlyArtifactStore
from .gate import ProductionReadyError, require_production_ready, transition_environment
from .modes import EnvironmentTransitionError, normalize_environment
from .protocol import LiveReadonlySession, TradingEnvironment
from .session import assert_session_locked, merge_session_update, open_session
from .snapshot import capture_broker_snapshot
from .writers import LiveReadonlyWriter


class LiveReadonlyError(RuntimeError):
    """Live Readonly 服务错误。"""


class LiveReadonlyService:
    """只读 Live 编排：禁止 submit/cancel/replace；不注入 OMS broker_port。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        adapter: LiveReadonlyAdapter | None = None,
        safety_service: Any = None,
        recon_service: Any = None,
        ops_service: Any = None,
        artifact_store: LiveReadonlyArtifactStore | None = None,
    ) -> None:
        # 故意不接受 oms_service / broker_port，避免发单路径
        self._store = store
        self._registry = registry
        self._adapter = adapter
        self._safety = safety_service
        self._recon = recon_service
        self._ops = ops_service
        self._writer = LiveReadonlyWriter(registry, artifact_store=artifact_store)
        self._session: LiveReadonlySession | None = None
        self._environment: TradingEnvironment = "PAPER"

    @property
    def adapter(self) -> LiveReadonlyAdapter:
        if self._adapter is None:
            self._adapter = LiveReadonlyAdapter(registry=self._registry)
        return self._adapter

    def assert_environment(self, expected: str) -> TradingEnvironment:
        env = normalize_environment(expected)
        if self._environment != env:
            raise LiveReadonlyError(
                f"environment mismatch: current={self._environment!r}, expected={env!r}"
            )
        return env

    def set_environment(
        self, to_env: str, *, account_id: str = "", actor: str = "operator"
    ) -> TradingEnvironment:
        """经 Safety Gate 阶梯转换当前环境。"""
        dst = transition_environment(
            from_env=self._environment,
            to_env=to_env,
            registry=self._registry,
            ops_service=self._ops,
            account_id=account_id,
            actor=actor,
        )
        self._environment = dst
        if account_id:
            self._writer.upsert_environment_state(account_id, dst)
        return dst

    def connect(self) -> None:
        """PRODUCTION_READY + Live 凭证 + 只读探测。"""
        require_production_ready(self._registry)
        self.adapter.connect()

    def disconnect(self) -> None:
        self.adapter.disconnect()

    def health(self) -> dict[str, Any]:
        connected = getattr(self.adapter, "_connected", False)
        return {
            "environment": self._environment,
            "connected": bool(connected),
            "broker_id": self.adapter.broker_id,
            "readonly": True,
        }

    def get_account(self):
        return self.adapter.get_account()

    def get_positions(self):
        return self.adapter.get_positions()

    def get_orders(self):
        return self.adapter.get_open_orders()

    def get_executions(self):
        return self.adapter.recent_executions()

    def capture_snapshot(self, *, account_id: str = "", salt: str = "") -> BrokerSnapshot:
        acct = account_id or (self._session.account_id if self._session else "")
        if not acct:
            view = self.adapter.get_account()
            acct = view.account_id or "unknown"
        snap = capture_broker_snapshot(self.adapter, account_id=acct, salt=salt)
        uri, cs = self._writer._artifacts.write_snapshot(snap)
        snap = snap.model_copy(update={"raw_storage_uri": uri})
        sid = self._session.session_id if self._session else ""
        self._writer.write_snapshot_index(
            snap, session_id=sid, storage_uri=uri, checksum=cs
        )
        return snap

    def reconcile_observe(
        self, account_id: str, portfolio_id: str, **kwargs: Any
    ) -> ReconciliationRun:
        """6F 对账观察模式：产生 Finding，不通过本服务发单。"""
        if self._recon is None:
            raise LiveReadonlyError("recon_service not configured")
        # 临时将对账 adapter 指向 live readonly（只读）
        orig = getattr(self._recon, "_adapter", None)
        try:
            self._recon._adapter = self.adapter
            return self._recon.run(
                account_id,
                portfolio_id,
                mode=kwargs.get("mode", "FAST"),
                inject=kwargs.get("inject"),
                salt=kwargs.get("salt", ""),
            )
        finally:
            if orig is not None:
                self._recon._adapter = orig

    def start_session(
        self,
        *,
        account_id: str,
        portfolio_id: str = "",
        trading_date: str = "",
        dataset_hash: str,
        model_version: str,
        strategy_version: str,
        salt: str = "",
    ) -> LiveReadonlySession:
        """打开 LIVE_READONLY 会话并锁定版本字段。"""
        self.set_environment("LIVE_READONLY", account_id=account_id)
        session = open_session(
            account_id=account_id,
            portfolio_id=portfolio_id,
            trading_date=trading_date,
            dataset_hash=dataset_hash,
            model_version=model_version,
            strategy_version=strategy_version,
            salt=salt,
        )
        self._session = session
        self._writer.write_session(session)
        return session

    def lock_check(
        self,
        *,
        dataset_hash: str | None = None,
        model_version: str | None = None,
        strategy_version: str | None = None,
    ) -> None:
        if self._session is None:
            raise LiveReadonlyError("no active session")
        assert_session_locked(
            self._session,
            dataset_hash=dataset_hash,
            model_version=model_version,
            strategy_version=strategy_version,
        )

    def close_session(self) -> LiveReadonlySession:
        if self._session is None:
            raise LiveReadonlyError("no active session")
        closed = merge_session_update(self._session, {"status": "CLOSED"})
        self._session = closed
        self._writer.write_session(closed)
        return closed


__all__ = [
    "LiveReadonlyError",
    "LiveReadonlyService",
    "ProductionReadyError",
    "EnvironmentTransitionError",
    "fake_adapter",
]
