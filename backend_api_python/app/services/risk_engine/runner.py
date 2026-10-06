"""RiskEngineService：evaluate / register_policy。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from app.services.portfolio_service.protocol import (
    Account,
    ApplyTargetsResult,
    Position,
    PositionDelta,
)
from app.services.research_data.contracts import Signal, TargetPosition
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import RiskArtifactStore
from .context import build_context
from .cycle import run_evaluate
from .policy import finalize_policy, from_bundle_meta, parse_policy_ref
from .protocol import ENGINE_VERSION, RiskEvaluateResult, RiskPolicy
from .writers import RiskWriter


class RiskEngineError(RuntimeError):
    """Risk Engine 编排错误。"""


class RiskEngineService:
    """独立风控引擎；停在 OrderIntent。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        artifact_store: RiskArtifactStore | None = None,
        rules: Sequence[Any] | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._writer = RiskWriter(registry, artifact_store=artifact_store)
        self._rules = list(rules) if rules is not None else None

    def register_policy(self, policy: RiskPolicy) -> RiskPolicy:
        pol = finalize_policy(policy)
        self._writer.write_policy(pol)
        return pol

    def get_policy(self, policy_code: str, version: str) -> RiskPolicy:
        summary = self._registry.get_risk_policy(policy_code, version)
        meta = dict(summary.metadata or {})
        return finalize_policy(
            RiskPolicy(
                policy_code=summary.policy_code,
                policy_version=summary.policy_version,
                policy_hash=summary.policy_hash,
                max_single_position_weight=float(
                    meta.get("max_single_position_weight") or 0.10
                ),
                max_gross_exposure=float(meta.get("max_gross_exposure") or 1.0),
                max_turnover=float(meta.get("max_turnover") or 0.30),
                max_position_delta_weight=float(
                    meta.get("max_position_delta_weight") or 0.05
                ),
                clip_on_limit=bool(
                    meta["clip_on_limit"]
                    if meta.get("clip_on_limit") is not None
                    else True
                ),
                engine_version=summary.engine_version or ENGINE_VERSION,
                metadata=meta,
            )
        )

    def evaluate(
        self,
        apply_result: ApplyTargetsResult | None = None,
        *,
        deltas: Sequence[PositionDelta] | None = None,
        account: Account | None = None,
        positions: Sequence[Position] | Mapping[str, Position] | None = None,
        targets: Sequence[TargetPosition] | None = None,
        policy: RiskPolicy | None = None,
        policy_ref: str | None = None,
        trading_status: Mapping[str, Mapping[str, Any]] | None = None,
        prices: Mapping[str, float] | None = None,
        signals: Sequence[Signal] | None = None,
        knowledge_time: datetime | None = None,
        market_data_as_of: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RiskEvaluateResult:
        """消费 6B apply / deltas → OrderIntent。"""
        meta = dict(metadata or {})
        pol = policy
        if pol is None and policy_ref:
            code, ver = parse_policy_ref(policy_ref)
            pol = self.get_policy(code, ver)
        if pol is None:
            pol = from_bundle_meta(meta)

        ctx = build_context(
            apply_result=apply_result,
            deltas=deltas,
            account=account,
            positions=positions,
            targets=targets,
            policy=pol,
            trading_status=trading_status,
            prices=prices,
            signals=signals,
            knowledge_time=knowledge_time,
            market_data_as_of=market_data_as_of,
            metadata=meta,
        )
        # 注册策略（幂等 upsert）
        try:
            self._writer.write_policy(ctx.policy)
        except Exception:
            pass
        return run_evaluate(
            ctx,
            writer=self._writer,
            registry=self._registry,
            rules=self._rules,
            metadata=meta,
        )
