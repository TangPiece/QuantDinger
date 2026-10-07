"""Phase 7E：TradingGovernanceService 门面（Gradual Scale / 多策略多账户）。"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

from app.services.live_readonly.gate import is_production_ready
from app.services.research_data.registry import ResearchRegistry

from .account_registry import (
    assert_strategy_account_bind,
    register_account,
)
from .aggregation import aggregate_targets
from .approval import approve_record, new_approval
from .attribution import attribute_positions_from_legs
from .capital import CapitalReject, check_order_notional, validate_allocation
from .capacity import check_capacity
from .lifecycle import LifecycleTransitionError, assert_transition as assert_lc_transition
from .protocol import (
    AccountRegistryEntry,
    CapacityLimit,
    CapitalAllocation,
    EffectiveCaps,
    GovernanceApproval,
    OrderRiskContext,
    PortfolioTarget,
    RiskBudgetLayer,
    RiskBudgetLayers,
    ScaleLevel,
    ScaleState,
    StrategyAccountBind,
    StrategyLifecycleRecord,
    StrategyTarget,
    StrategyVersionPin,
)
from .resolver import resolve_effective_caps
from .risk_budget import RiskBudgetReject, check_order_layers
from .rollback import rollback_strategy_version
from .scale import evaluate_scale_up_criteria, next_level
from .strategy_registry import (
    assert_version_immutable,
    register_version_pin,
)
from .writers import GovernanceWriter


class GovernanceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TradingGovernanceService:
    """Live Trading Governance Layer；禁止无审批升档与 PnL 自动放量。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        safety: Any | None = None,
        controlled: Any | None = None,
        ops: Any | None = None,
        writer: GovernanceWriter | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._safety = safety
        self._controlled = controlled
        self._ops = ops
        self._writer = writer or GovernanceWriter(registry)
        # 进程内状态（CI Fake；D1 经 writer 持久化索引）
        self._versions: dict[tuple[str, str], StrategyVersionPin] = {}
        self._lifecycle: dict[str, StrategyLifecycleRecord] = {}
        self._capital: dict[tuple[str, str], CapitalAllocation] = {}
        self._risk: dict[str, RiskBudgetLayers] = {}
        self._capacity: dict[str, CapacityLimit] = {}
        self._scale: dict[str, ScaleState] = {}
        self._accounts: dict[str, AccountRegistryEntry] = {}
        self._binds: dict[str, StrategyAccountBind] = {}
        self._live_env_approved_accounts: set[str] = set()
        self._pending_scale_approvals: dict[str, GovernanceApproval] = {}

    def register_strategy_version(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        model_version: str = "",
        dataset_hash: str = "",
        feature_version: str = "",
        is_live: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> StrategyVersionPin:
        key = (strategy_id, strategy_version)
        existing = self._versions.get(key)
        pin = register_version_pin(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            model_version=model_version,
            dataset_hash=dataset_hash,
            feature_version=feature_version,
            is_live=is_live,
            metadata=metadata,
        )
        if existing is not None:
            assert_version_immutable(existing, pin.model_dump())
        self._versions[key] = pin
        self._writer.write_strategy_version(pin)
        if strategy_id not in self._lifecycle:
            self._lifecycle[strategy_id] = StrategyLifecycleRecord(
                strategy_id=strategy_id,
                state="DRAFT",
                active_version=strategy_version,
                updated_at=_now(),
            )
            self._writer.write_lifecycle(self._lifecycle[strategy_id])
        return pin

    def transition_lifecycle(
        self,
        strategy_id: str,
        to_state: str,
        *,
        live_go_live_approved: bool = False,
    ) -> StrategyLifecycleRecord:
        lc = self._lifecycle.get(strategy_id)
        if lc is None:
            raise GovernanceError("strategy not registered")
        scale = lc.scale_level
        try:
            assert_lc_transition(
                lc.state,  # type: ignore[arg-type]
                to_state,  # type: ignore[arg-type]
                scale_level=scale,
                live_go_live_approved=live_go_live_approved,
            )
        except LifecycleTransitionError as exc:
            raise GovernanceError(str(exc)) from exc
        lc = lc.model_copy(
            update={"state": to_state, "updated_at": _now()}  # type: ignore[arg-type]
        )
        self._lifecycle[strategy_id] = lc
        self._writer.write_lifecycle(lc)
        return lc

    def allocate_capital(
        self,
        *,
        account_id: str,
        strategy_id: str,
        allocated_notional: float,
        reserve_notional: float = 0.0,
    ) -> CapitalAllocation:
        rec = CapitalAllocation(
            account_id=account_id,
            strategy_id=strategy_id,
            allocated_notional=allocated_notional,
            reserve_notional=reserve_notional,
        )
        validate_allocation(rec)
        self._capital[(account_id, strategy_id)] = rec
        from app.services.research_data.contracts import GovCapitalAllocationSummary

        self._registry.upsert_gov_capital_allocation(
            GovCapitalAllocationSummary(
                account_id=account_id,
                strategy_id=strategy_id,
                allocated_notional=allocated_notional,
                reserve_notional=reserve_notional,
                used_notional=rec.used_notional,
                engine_version="qd_governance@1",
            )
        )
        return rec

    def set_risk_budget(self, layers: RiskBudgetLayers) -> RiskBudgetLayers:
        self._risk[layers.strategy_id or layers.account_id] = layers
        from app.services.research_data.contracts import GovRiskBudgetSummary

        self._registry.upsert_gov_risk_budget(
            GovRiskBudgetSummary(
                account_id=layers.account_id,
                portfolio_id=layers.portfolio_id,
                strategy_id=layers.strategy_id,
                layers_json=[x.model_dump(mode="json") for x in layers.layers],
                engine_version="qd_governance@1",
            )
        )
        return layers

    def set_capacity(self, cap: CapacityLimit) -> CapacityLimit:
        self._capacity[cap.strategy_id] = cap
        from app.services.research_data.contracts import GovCapacitySummary

        self._registry.upsert_gov_capacity(
            GovCapacitySummary(
                strategy_id=cap.strategy_id,
                max_notional=cap.max_notional,
                max_order_size=cap.max_order_size,
                max_participation_rate=cap.max_participation_rate,
                max_daily_turnover=cap.max_daily_turnover,
                engine_version="qd_governance@1",
            )
        )
        return cap

    def request_scale_up(
        self,
        strategy_id: str,
        *,
        account_id: str = "",
        metrics: Mapping[str, Any] | None = None,
    ) -> GovernanceApproval:
        """升档请求：仅生成 criteria report + PENDING 审批，绝不自动 apply。"""
        lc = self._lifecycle.get(strategy_id)
        base_level = lc.scale_level if lc else "L0_SHADOW"
        st = self._scale.get(strategy_id) or ScaleState(
            strategy_id=strategy_id,
            account_id=account_id,
            current_level=base_level,  # type: ignore[arg-type]
        )
        self._scale[strategy_id] = st
        nxt = next_level(st.current_level)
        if nxt is None:
            raise GovernanceError("already at max scale level")
        report = evaluate_scale_up_criteria(
            strategy_id=strategy_id,
            from_level=st.current_level,
            to_level=nxt,
            metrics=metrics,
        )
        # 即使 criteria_met=True 也不自动升档
        appr = new_approval(
            kind="SCALE_UP",
            strategy_id=strategy_id,
            account_id=account_id or st.account_id,
            from_scale=st.current_level,
            to_scale=nxt,
            status="PENDING",
        )
        appr = appr.model_copy(
            update={"metadata": {"criteria_report": report.model_dump(mode="json")}}
        )
        self._pending_scale_approvals[appr.approval_id] = appr
        st = st.model_copy(update={"pending_level": nxt, "updated_at": _now()})
        self._scale[strategy_id] = st
        self._writer.write_scale_state(st)
        return appr

    def approve_scale(
        self,
        approval_id: str,
        *,
        operator: str,
        approval_token: str = "",
    ) -> GovernanceApproval:
        appr = self._pending_scale_approvals.get(approval_id)
        if appr is None:
            raise GovernanceError("approval not found")
        appr = approve_record(appr, operator=operator, token=approval_token)
        self._pending_scale_approvals[approval_id] = appr
        self._writer.write_approval(appr)
        return appr

    def apply_scale(self, strategy_id: str, *, approval_id: str) -> ScaleState:
        appr = self._pending_scale_approvals.get(approval_id)
        if appr is None or appr.status != "APPROVED":
            raise GovernanceError("approved scale_up required")
        if appr.strategy_id != strategy_id:
            raise GovernanceError("strategy_id mismatch")
        to_level = appr.to_scale  # type: ignore[assignment]
        st = self._scale.get(strategy_id) or ScaleState(strategy_id=strategy_id)
        st = st.model_copy(
            update={
                "current_level": to_level,
                "pending_level": None,
                "updated_at": _now(),
            }
        )
        self._scale[strategy_id] = st
        self._writer.write_scale_state(st)
        lc = self._lifecycle.get(strategy_id)
        if lc is not None:
            lc = lc.model_copy(update={"scale_level": to_level, "updated_at": _now()})
            self._lifecycle[strategy_id] = lc
            self._writer.write_lifecycle(lc)
        return st

    def register_account(
        self, account_id: str, **kwargs: Any
    ) -> AccountRegistryEntry:
        ent = register_account(account_id, **kwargs)
        self._accounts[account_id] = ent
        from app.services.research_data.contracts import GovAccountRegistrySummary

        self._registry.upsert_gov_account_registry(
            GovAccountRegistrySummary(
                account_id=account_id,
                label=ent.label,
                environment=ent.environment,
                status=ent.status,
                engine_version="qd_governance@1",
            )
        )
        return ent

    def bind_strategy_account(
        self, strategy_id: str, account_id: str, *, portfolio_id: str = ""
    ) -> StrategyAccountBind:
        bind = StrategyAccountBind(
            strategy_id=strategy_id,
            account_id=account_id,
            portfolio_id=portfolio_id,
        )
        self._binds[strategy_id] = bind
        from app.services.research_data.contracts import GovStrategyAccountBindSummary

        self._registry.upsert_gov_strategy_account_bind(
            GovStrategyAccountBindSummary(
                strategy_id=strategy_id,
                account_id=account_id,
                portfolio_id=portfolio_id,
                engine_version="qd_governance@1",
            )
        )
        return bind

    def aggregate_targets(
        self, strategy_targets: Sequence[StrategyTarget], *, account_id: str
    ) -> list[PortfolioTarget]:
        targets = aggregate_targets(account_id, tuple(strategy_targets))
        run_id = "agg_" + uuid4().hex[:12]
        self._writer.write_aggregation_run(
            account_id=account_id, run_id=run_id, targets=tuple(targets)
        )
        return targets

    def attribute_positions(
        self, account_id: str, legs: Sequence[Mapping[str, object]] | None = None
    ) -> list:
        rows = attribute_positions_from_legs(account_id, legs or ())
        from app.services.research_data.contracts import GovAttributionSnapshotSummary

        snap_id = "attr_" + uuid4().hex[:12]
        self._registry.upsert_gov_attribution_snapshot(
            GovAttributionSnapshotSummary(
                snapshot_id=snap_id,
                account_id=account_id,
                rows_json=[r.model_dump(mode="json") for r in rows],
                engine_version="qd_governance@1",
            )
        )
        return rows

    def rollback_strategy(
        self, strategy_id: str, *, to_version: str
    ) -> tuple[StrategyLifecycleRecord, StrategyVersionPin]:
        lc = self._lifecycle.get(strategy_id)
        if lc is None:
            raise GovernanceError("strategy not registered")
        active_key = (strategy_id, lc.active_version)
        prev_key = (strategy_id, to_version)
        pin = self._versions.get(active_key)
        prev = self._versions.get(prev_key)
        if pin is None:
            raise GovernanceError("active version pin missing")
        new_lc, new_pin = rollback_strategy_version(lc, pin, to_version=to_version, previous_pin=prev)
        self._lifecycle[strategy_id] = new_lc
        self._versions[prev_key] = new_pin
        self._writer.write_lifecycle(new_lc)
        self._writer.write_strategy_version(new_pin)
        return new_lc, new_pin

    def effective_caps(self, account_id: str, strategy_id: str) -> EffectiveCaps:
        st = self._scale.get(strategy_id)
        level: ScaleLevel = (
            st.current_level if st else self._lifecycle.get(strategy_id, StrategyLifecycleRecord(strategy_id=strategy_id)).scale_level  # noqa: E501
        )
        cap = self._capacity.get(strategy_id)
        capital = self._capital.get((account_id, strategy_id))
        live_ok = account_id in self._live_env_approved_accounts and level == "L4_PRODUCTION"
        return resolve_effective_caps(
            account_id=account_id,
            strategy_id=strategy_id,
            scale_level=level,
            capital=capital,
            capacity=cap,
            live_env_authorized=live_ok,
        )

    def authorize_live_environment(
        self,
        account_id: str,
        *,
        strategy_id: str,
        operator: str,
        approval_token: str = "",
    ) -> GovernanceApproval:
        """L4 + PRODUCTION_READY + LIVE_ENV 双重审批后才允许 LIVE ladder。"""
        if not is_production_ready(self._registry):
            raise GovernanceError("PRODUCTION_READY required for LIVE_ENV")
        st = self._scale.get(strategy_id)
        if st is None or st.current_level != "L4_PRODUCTION":
            raise GovernanceError("L4_PRODUCTION scale required")
        env_flag = (os.environ.get("LIVE_ENV_APPROVAL") or "").strip().lower()
        if env_flag not in ("true", "1", "yes", "on"):
            raise GovernanceError("LIVE_ENV_APPROVAL env required")
        appr = new_approval(
            kind="LIVE_ENV",
            strategy_id=strategy_id,
            account_id=account_id,
            operator_actor=operator,
            approval_token=approval_token,
            status="APPROVED",
        )
        self._live_env_approved_accounts.add(account_id)
        if st is not None:
            st = st.model_copy(update={"live_env_approved": True, "updated_at": _now()})
            self._scale[strategy_id] = st
            self._writer.write_scale_state(st)
        self._writer.write_approval(appr)
        return appr

    def is_live_authorized(self, account_id: str, strategy_id: str = "") -> bool:
        """供 modes/Gateway/OMS 查询 LIVE 是否已 governance 授权。"""
        if account_id not in self._live_env_approved_accounts:
            return False
        if strategy_id:
            st = self._scale.get(strategy_id)
            if st is None or st.current_level != "L4_PRODUCTION":
                return False
        return is_production_ready(self._registry)

    def check_order_allowed(
        self,
        ctx: OrderRiskContext,
        *,
        session_notional_used: float = 0.0,
        order_count: int = 0,
    ) -> None:
        """Capital + Risk + Capacity + Account bind 统一 REJECT。"""
        bind = self._binds.get(ctx.strategy_id)
        assert_strategy_account_bind(bind, account_id=ctx.account_id, strategy_id=ctx.strategy_id)
        cap_rec = self._capital.get((ctx.account_id, ctx.strategy_id))
        if cap_rec is not None:
            ok, reason = check_order_notional(cap_rec, notional=ctx.notional)
            if not ok:
                raise CapitalReject(reason)
        rb = self._risk.get(ctx.strategy_id) or self._risk.get(ctx.account_id)
        if rb is not None:
            ok, reason = check_order_layers(
                rb,
                ctx,
                session_notional_used=session_notional_used,
                order_count=order_count,
            )
            if not ok:
                raise RiskBudgetReject(reason)
        cap_lim = self._capacity.get(ctx.strategy_id)
        if cap_lim is not None:
            ok, reason = check_capacity(cap_lim, ctx)
            if not ok:
                raise RiskBudgetReject(reason)

    def default_risk_layers(
        self,
        *,
        account_id: str,
        strategy_id: str,
        account_max: float,
        strategy_max: float,
    ) -> RiskBudgetLayers:
        """测试/golden 用四层预算骨架。"""
        return RiskBudgetLayers(
            account_id=account_id,
            strategy_id=strategy_id,
            layers=(
                RiskBudgetLayer(scope="ACCOUNT", scope_id=account_id, max_exposure=account_max),
                RiskBudgetLayer(scope="STRATEGY", scope_id=strategy_id, max_exposure=strategy_max),
                RiskBudgetLayer(
                    scope="ORDER",
                    scope_id=strategy_id,
                    max_exposure=strategy_max,
                    max_notional=strategy_max,
                ),
            ),
        )
