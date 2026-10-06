"""PortfolioService：open_account / bind_runtime / apply_targets。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.services.research_data.contracts import TargetPosition
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import PortfolioArtifactStore
from .cycle import run_apply_targets
from .hash import compute_account_id, compute_portfolio_id
from .protocol import (
    ENGINE_VERSION,
    Account,
    ApplyMode,
    ApplyTargetsResult,
    CashBalance,
    Portfolio,
    PortfolioEnvironment,
    PortfolioMarket,
    PortfolioSnapshot,
    PortfolioState,
    Position,
    PnL,
)
from .reconciliation import PortfolioReconciliation, ReconciliationReport
from .snapshot import recover, state_from_snapshot
from .state_machine import PortfolioStateError, is_applyable
from .writers import PortfolioWriter


class PortfolioServiceError(RuntimeError):
    """Portfolio Service 编排错误。"""


class PortfolioService:
    """生产账户/持仓 SSOT；停在 PositionDelta（PAPER 可极简成交）。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        artifact_store: PortfolioArtifactStore | None = None,
        market_data: Any = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._market_data = market_data
        self._writer = PortfolioWriter(registry, artifact_store=artifact_store)
        self._recon = PortfolioReconciliation()

    def open_account(
        self,
        *,
        environment: PortfolioEnvironment | str = "PAPER",
        market: PortfolioMarket | str = "CN_A",
        initial_cash: float = 1_000_000.0,
        currency: str = "CNY",
        metadata: dict[str, Any] | None = None,
    ) -> Account:
        env = str(environment)
        if env not in ("PAPER", "SHADOW"):
            raise PortfolioServiceError(
                f"environment must be PAPER|SHADOW, got {env!r}"
            )
        now = datetime.now(timezone.utc).isoformat()
        salt = now
        aid = compute_account_id(environment=env, market=str(market), salt=salt)
        cash = CashBalance(
            currency=currency,
            available_cash=float(initial_cash),
            frozen_cash=0.0,
        )
        account = Account(
            account_id=aid,
            environment=env,  # type: ignore[arg-type]
            market=str(market),  # type: ignore[arg-type]
            status="ACTIVE",
            currency=currency,
            cash=cash,
            market_value=0.0,
            equity=float(initial_cash),
            pnl=PnL(),
            engine_version=ENGINE_VERSION,
            created_at=now,
            metadata=dict(metadata or {}),
        ).recompute_equity()
        self._writer.write_account(account)
        # 默认组合
        pid = compute_portfolio_id(account_id=aid, label="default")
        pf = Portfolio(
            portfolio_id=pid,
            account_id=aid,
            status="ACTIVE",
            engine_version=ENGINE_VERSION,
            created_at=now,
        )
        self._writer.write_portfolio(pf)
        meta = dict(account.metadata or {})
        meta["default_portfolio_id"] = pid
        account = account.model_copy(update={"metadata": meta})
        self._writer.write_account(account)
        return account

    def bind_runtime(
        self,
        account_id: str,
        runtime_id: str,
        *,
        bundle_hash: str = "",
        portfolio_id: str | None = None,
    ) -> Portfolio:
        account = self._load_account(account_id)
        pid = portfolio_id or str(
            (account.metadata or {}).get("default_portfolio_id") or ""
        )
        if not pid:
            pid = compute_portfolio_id(account_id=account_id, runtime_id=runtime_id)
        try:
            existing = self._registry.get_production_portfolio(pid)
            pf = Portfolio(
                portfolio_id=existing.portfolio_id,
                account_id=existing.account_id,
                runtime_id=runtime_id,
                bundle_hash=bundle_hash or existing.bundle_hash,
                status=existing.status,  # type: ignore[arg-type]
                trading_date=existing.trading_date,
                engine_version=existing.engine_version or ENGINE_VERSION,
                storage_uri=existing.storage_uri,
                created_at=existing.created_at,
                metadata=dict(existing.metadata or {}),
            )
        except KeyError:
            pf = Portfolio(
                portfolio_id=pid,
                account_id=account_id,
                runtime_id=runtime_id,
                bundle_hash=bundle_hash,
                status="ACTIVE",
                engine_version=ENGINE_VERSION,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        self._writer.write_portfolio(pf)
        return pf

    def apply_targets(
        self,
        account_id: str,
        targets: Sequence[TargetPosition],
        *,
        runtime_id: str = "",
        run_id: str = "",
        trading_date: str | None = None,
        prices: Mapping[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
        portfolio_id: str | None = None,
        apply_mode: ApplyMode | None = None,
        corporate_actions: Sequence[Any] | None = None,
    ) -> ApplyTargetsResult:
        account = self._load_account(account_id)
        if not is_applyable(account.status):
            raise PortfolioServiceError(
                f"account not applyable: {account.status}"
            )
        meta = dict(metadata or {})
        pid = portfolio_id or str(
            (account.metadata or {}).get("default_portfolio_id") or ""
        )
        if not pid:
            raise PortfolioServiceError("portfolio_id required")
        portfolio = self._load_portfolio(pid)
        positions = self._load_positions(pid)
        state = PortfolioState(
            account=account, portfolio=portfolio, positions=positions
        )

        td = trading_date or portfolio.trading_date
        if not td and targets:
            td = str(getattr(targets[0], "trading_date", "") or "")
        if not td:
            td = datetime.now(timezone.utc).date().isoformat()

        px = dict(prices or meta.get("prices") or {})
        if not px and meta.get("price_bars"):
            px = _prices_from_bars(meta["price_bars"], td)

        env = account.environment
        mode: ApplyMode = apply_mode or (
            "PAPER_FILL" if env == "PAPER" else "SHADOW_DRY"
        )
        if meta.get("apply_mode") in ("PAPER_FILL", "SHADOW_DRY"):
            mode = meta["apply_mode"]  # type: ignore[assignment]

        return run_apply_targets(
            state,
            list(targets),
            writer=self._writer,
            registry=self._registry,
            prices=px,
            trading_date=td,
            runtime_id=runtime_id or portfolio.runtime_id,
            run_id=run_id,
            apply_mode=mode,
            corporate_actions=corporate_actions or meta.get("corporate_actions"),
            metadata=meta,
        )

    def get_portfolio(self, portfolio_id: str) -> Portfolio:
        return self._load_portfolio(portfolio_id)

    def get_positions(self, portfolio_id: str) -> list[Position]:
        return list(self._load_positions(portfolio_id).values())

    def get_account(self, account_id: str) -> Account:
        return self._load_account(account_id)

    def get_snapshot(self, snapshot_id: str) -> PortfolioSnapshot:
        summary = self._registry.get_portfolio_snapshot(snapshot_id)
        # 轻量：从 summary 字段重建（positions 在 artifact；测试可只看元数据）
        return PortfolioSnapshot(
            snapshot_id=summary.snapshot_id,
            account_id=summary.account_id,
            portfolio_id=summary.portfolio_id,
            trading_date=summary.trading_date,
            knowledge_time=summary.knowledge_time,
            cash=float(summary.cash),
            market_value=float(summary.market_value),
            equity=float(summary.equity),
            realized_pnl=float(summary.realized_pnl),
            unrealized_pnl=float(summary.unrealized_pnl),
            total_pnl=float(summary.total_pnl),
            gross_exposure=float(summary.gross_exposure),
            net_exposure=float(summary.net_exposure),
            runtime_id=summary.runtime_id,
            bundle_hash=summary.bundle_hash,
            storage_uri=summary.storage_uri,
            metadata=dict(summary.metadata or {}),
        )

    def replay(
        self,
        snapshot_id: str,
        *,
        portfolio_id: str | None = None,
    ) -> PortfolioState:
        """从 snapshot + 后续 events 恢复。"""
        snap_summary = self._registry.get_portfolio_snapshot(snapshot_id)
        snap = self.get_snapshot(snapshot_id)
        # 尝试读 artifact positions.json
        snap = self._hydrate_snapshot_positions(snap)
        pid = portfolio_id or snap.portfolio_id
        account = self._load_account(snap.account_id)
        portfolio = self._load_portfolio(pid)
        events_raw = self._registry.list_position_events(pid, limit=2000)
        # 仅 replay snapshot 之后
        from .protocol import PositionEvent

        tail = []
        for e in events_raw:
            if (e.created_at or "") <= (snap_summary.created_at or snap.knowledge_time or ""):
                continue
            tail.append(
                PositionEvent(
                    event_id=e.event_id,
                    portfolio_id=e.portfolio_id,
                    account_id=e.account_id,
                    event_type=e.event_type,
                    instrument_key=e.instrument_key,
                    trading_date=e.trading_date,
                    quantity=float(e.quantity),
                    price=float(e.price),
                    cash_delta=float(e.cash_delta),
                    fee=float(e.fee),
                    idempotency_key=e.idempotency_key,
                    message=e.message,
                    payload=dict(e.payload_json or {}),
                    created_at=e.created_at,
                )
            )
        return recover(snap, tail, account=account, portfolio=portfolio)

    def reconcile(
        self,
        account_id: str,
        *,
        external_positions=None,
        external_cash=None,
        mark_status: bool = False,
    ) -> ReconciliationReport:
        account = self._load_account(account_id)
        pid = str((account.metadata or {}).get("default_portfolio_id") or "")
        positions = self._load_positions(pid) if pid else {}
        report = self._recon.compare(
            account,
            positions,
            external_positions=external_positions,
            external_cash=external_cash,
        )
        if mark_status and report.status == "RECONCILIATION_REQUIRED":
            from .reconciliation import mark_reconciliation_required

            account = mark_reconciliation_required(account)
            self._writer.write_account(account)
        return report

    def _load_account(self, account_id: str) -> Account:
        try:
            s = self._registry.get_production_account(account_id)
        except KeyError as exc:
            raise PortfolioServiceError(
                f"account not found: {account_id!r}"
            ) from exc
        return Account(
            account_id=s.account_id,
            environment=s.environment,  # type: ignore[arg-type]
            market=s.market,  # type: ignore[arg-type]
            status=s.status,  # type: ignore[arg-type]
            currency=s.currency,
            cash=CashBalance(
                currency=s.currency,
                available_cash=float(s.available_cash),
                frozen_cash=float(s.frozen_cash),
            ),
            market_value=float(s.market_value),
            equity=float(s.equity),
            pnl=PnL(
                realized_pnl=float(s.realized_pnl),
                unrealized_pnl=float(s.unrealized_pnl),
            ),
            engine_version=s.engine_version or ENGINE_VERSION,
            storage_uri=s.storage_uri,
            created_at=s.created_at,
            metadata=dict(s.metadata or {}),
        )

    def _load_portfolio(self, portfolio_id: str) -> Portfolio:
        try:
            s = self._registry.get_production_portfolio(portfolio_id)
        except KeyError as exc:
            raise PortfolioServiceError(
                f"portfolio not found: {portfolio_id!r}"
            ) from exc
        return Portfolio(
            portfolio_id=s.portfolio_id,
            account_id=s.account_id,
            runtime_id=s.runtime_id,
            bundle_hash=s.bundle_hash,
            status=s.status,  # type: ignore[arg-type]
            trading_date=s.trading_date,
            engine_version=s.engine_version or ENGINE_VERSION,
            storage_uri=s.storage_uri,
            created_at=s.created_at,
            metadata=dict(s.metadata or {}),
        )

    def _load_positions(self, portfolio_id: str) -> dict[str, Position]:
        rows = self._registry.list_positions(portfolio_id)
        out: dict[str, Position] = {}
        for r in rows:
            out[r.instrument_key] = Position(
                instrument_key=r.instrument_key,
                quantity=float(r.quantity),
                available_quantity=float(r.available_quantity),
                frozen_quantity=float(r.frozen_quantity),
                avg_cost=float(r.avg_cost),
                market_value=float(r.market_value),
                currency=r.currency,
                as_of=r.as_of,
                metadata=dict(r.metadata or {}),
            )
        return out

    def _hydrate_snapshot_positions(self, snap: PortfolioSnapshot) -> PortfolioSnapshot:
        if snap.positions or not snap.storage_uri:
            return snap
        from pathlib import Path
        import json

        path = Path(snap.storage_uri) / "positions.json"
        if not path.is_file():
            return snap
        raw = json.loads(path.read_text(encoding="utf-8"))
        from .protocol import PositionSnapshot

        positions = [PositionSnapshot.model_validate(x) for x in raw]
        return snap.model_copy(update={"positions": positions})


def _prices_from_bars(bars: Sequence[Any], trading_date: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in bars:
        d = dict(r) if not isinstance(r, dict) else r
        td = str(d.get("trading_date") or "")[:10]
        if td and td != trading_date[:10]:
            continue
        key = str(d.get("instrument_key") or d.get("instrument") or "")
        px = d.get("close") if d.get("close") is not None else d.get("open")
        if key and px is not None:
            out[key] = float(px)
    return out
