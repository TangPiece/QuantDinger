"""可选：实现 6A RiskGatePort，委托 6C RiskEngine。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from app.services.research_data.contracts import Signal, TargetPosition
from app.services.research_data.production_bridge.protocol import GateResult

from .policy import from_bundle_meta
from .protocol import RiskEvaluateResult
from .runner import RiskEngineService


class SixCRiskGatePort:
    """6A RiskGatePort 适配器：将 signals/targets 转薄 evaluate。"""

    def __init__(self, engine: RiskEngineService) -> None:
        self._engine = engine

    def evaluate(
        self,
        signals: Sequence[Signal],
        targets: Sequence[TargetPosition],
        ctx: Mapping[str, Any] | None = None,
    ) -> GateResult:
        c = dict(ctx or {})
        # 从 targets 构造粗 deltas（无持仓时 current=0）
        from app.services.portfolio_service.protocol import PositionDelta

        deltas = []
        for t in targets:
            tw = float(t.target_weight or 0.0)
            tq = float(t.target_quantity or 0.0)
            side = "BUY" if tw > 0 or tq > 0 else ("FLAT" if tw == 0 and tq == 0 else "SELL")
            deltas.append(
                PositionDelta(
                    instrument_key=t.instrument_key,
                    current_weight=0.0,
                    target_weight=tw,
                    delta_weight=tw,
                    current_quantity=0.0,
                    target_quantity=tq,
                    delta_quantity=tq,
                    side=side,  # type: ignore[arg-type]
                )
            )
        policy = from_bundle_meta(c)
        result: RiskEvaluateResult = self._engine.evaluate(
            deltas=deltas,
            targets=list(targets),
            signals=list(signals),
            policy=policy,
            prices=c.get("prices"),
            trading_status=c.get("trading_status"),
            knowledge_time=c.get("now")
            if isinstance(c.get("now"), datetime)
            else None,
            metadata={
                "universe_membership": c.get("universe_membership") or [],
                "require_universe": bool(c.get("universe_membership")),
                "force_new_run": True,
            },
        )
        passed = result.verdict not in ("REJECT", "ERROR")
        return GateResult(
            gate="risk_engine_6c",
            passed=passed,
            severity="P0" if not passed else "",
            message=result.verdict
            + (f":{result.violations[0].message}" if result.violations else ""),
            details={
                "verdict": result.verdict,
                "n_intents": len(result.order_intents),
                "risk_run_id": result.risk_run_id,
            },
        )
