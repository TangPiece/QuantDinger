"""Phase 7C：ControlledLiveGate — 全部硬条件满足才 ALLOW。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.services.live_readonly.gate import is_production_ready
from app.services.research_data.contracts import OrderIntent
from app.services.research_data.registry import ResearchRegistry

from .config import load_controlled_live_config
from .protocol import ControlledLiveConfig, ControlledSession, OperatorApproval


class ControlledLiveDenied(RuntimeError):
    """Gate 拒绝真实 submit。"""

    def __init__(self, reason: str, *, code: str = "CONTROLLED_LIVE_DENIED") -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str = ""
    code: str = "ALLOW"


def _symbol_from_intent(intent: OrderIntent) -> str:
    key = str(intent.instrument_key or "")
    if ":" in key:
        return key.split(":", 1)[1].upper()
    return key.upper()


def _hash_token(token: str) -> str:
    """审计仅存 hash，不落明文 approval_token。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def require_operator_approval(
    *,
    session: ControlledSession,
    operator: str,
    approval_token: str,
    scope: str = "SINGLE_ORDER",
) -> OperatorApproval:
    """写入审批记录（token 只存 hash）。"""
    from datetime import datetime, timezone
    from uuid import uuid4

    return OperatorApproval(
        approval_id="cappr_" + uuid4().hex[:16],
        session_id=session.session_id,
        operator_actor=operator,
        approval_token_hash=_hash_token(approval_token or ""),
        scope=scope,
        status="APPROVED",
        approved_at=datetime.now(timezone.utc).isoformat(),
        metadata={"environment": session.environment},
    )


class ControlledLiveGate:
    """单 intent 提交前全量校验；可选 SafetyService.decide。"""

    def __init__(
        self,
        registry: ResearchRegistry | None = None,
        *,
        config: ControlledLiveConfig | None = None,
        kill_switch_checker: Any | None = None,
        safety: Any | None = None,
    ) -> None:
        self._registry = registry
        self._config = config or load_controlled_live_config()
        self._kill_switch_checker = kill_switch_checker
        self._safety = safety

    def evaluate(
        self,
        *,
        environment: str,
        session: ControlledSession,
        intent: OrderIntent,
        quote: Mapping[str, Any] | None = None,
        approval: OperatorApproval | None = None,
        notional_override: float | None = None,
    ) -> GateDecision:
        env = str(environment or "").strip().upper()
        if env != "LIVE_CONTROLLED":
            return GateDecision(False, "environment must be LIVE_CONTROLLED", "CONTROLLED_LIVE_DENIED")
        if env == "LIVE":
            return GateDecision(False, "LIVE forbidden in Phase 7C", "CONTROLLED_LIVE_DENIED")

        if not is_production_ready(self._registry):
            return GateDecision(False, "PRODUCTION_READY required", "CONTROLLED_LIVE_DENIED")

        cfg = session.config if session.config else self._config
        sym = _symbol_from_intent(intent)
        if sym not in {s.upper() for s in cfg.allowed_symbols}:
            return GateDecision(False, f"symbol {sym!r} not allowed", "CONTROLLED_LIVE_DENIED")

        side = str(intent.side or "").upper()
        if side not in {s.upper() for s in cfg.allowed_sides}:
            return GateDecision(False, f"side {side!r} not allowed", "CONTROLLED_LIVE_DENIED")

        otype = str(intent.execution_algorithm or "MARKET").upper()
        if otype not in {t.upper() for t in cfg.allowed_order_types}:
            return GateDecision(False, f"order_type {otype!r} not allowed (LIMIT only)", "CONTROLLED_LIVE_DENIED")
        if otype == "MARKET":
            return GateDecision(False, "MARKET orders forbidden", "CONTROLLED_LIVE_DENIED")

        qty = float(intent.quantity or 0)
        if qty <= 0 or qty > cfg.max_quantity:
            return GateDecision(False, "quantity exceeds max_quantity", "CONTROLLED_LIVE_DENIED")

        if session.order_count >= cfg.max_orders:
            return GateDecision(False, "session max_orders reached", "CONTROLLED_LIVE_DENIED")

        # approved_strategy_id 在 session 打开时锁定；runner 侧单独校验 strategy_id 参数

        if approval is None or approval.status != "APPROVED":
            return GateDecision(False, "operator approval required", "CONTROLLED_LIVE_DENIED")
        # SESSION 级审批可覆盖多笔；SINGLE_ORDER 仍要求 approval 存在
        scope = str(approval.scope or "SINGLE_ORDER").upper()
        if scope not in ("SINGLE_ORDER", "SESSION", "MULTI_ORDER"):
            return GateDecision(False, "invalid approval scope", "CONTROLLED_LIVE_DENIED")

        if self._safety is not None:
            try:
                sd = self._safety.decide(
                    session.account_id,
                    intent=intent,
                    strategy_id=session.approved_strategy_id,
                )
                if str(sd.decision).upper() != "ALLOW":
                    return GateDecision(
                        False,
                        sd.reason or "safety blocked",
                        "CONTROLLED_LIVE_DENIED",
                    )
            except Exception:
                return GateDecision(False, "safety fail-closed", "CONTROLLED_LIVE_DENIED")

        if self._kill_switch_engaged(session.account_id):
            return GateDecision(False, "kill_switch engaged", "CONTROLLED_LIVE_DENIED")

        limit_px = float(intent.limit_price or 0)
        if limit_px <= 0:
            return GateDecision(False, "LIMIT requires limit_price", "CONTROLLED_LIVE_DENIED")

        notional = notional_override if notional_override is not None else qty * limit_px
        if notional > cfg.max_notional:
            return GateDecision(False, "notional exceeds max_notional", "CONTROLLED_LIVE_DENIED")

        # 版本锁定
        if session.dataset_hash and intent.strategy_version:
            if session.strategy_version and intent.strategy_version != session.strategy_version:
                return GateDecision(False, "strategy_version mismatch", "CONTROLLED_LIVE_DENIED")

        _ = quote  # 预留：后续可校验 spread/stale
        return GateDecision(True, "ALLOW", "ALLOW")

    def _kill_switch_engaged(self, account_id: str) -> bool:
        if self._kill_switch_checker is not None:
            try:
                return bool(self._kill_switch_checker(account_id))
            except Exception:
                return True
        if self._registry is None:
            return False
        try:
            rec = self._registry.get_kill_switch("ACCOUNT", account_id or "global")
            return bool(rec.engaged)
        except Exception:
            return False

    def assert_allow(self, **kwargs: Any) -> GateDecision:
        decision = self.evaluate(**kwargs)
        if not decision.allowed:
            raise ControlledLiveDenied(decision.reason, code=decision.code)
        return decision
