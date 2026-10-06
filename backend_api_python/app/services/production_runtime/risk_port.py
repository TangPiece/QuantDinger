"""RiskGatePort：薄封装 5F SignalGate；完整 Risk Engine 留给 6C。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Protocol, Sequence

from app.services.research_data.contracts import Signal, TargetPosition
from app.services.research_data.production_bridge.protocol import GateResult
from app.services.research_data.production_bridge.signal_gate import run_signal_gate


class RiskGatePort(Protocol):
    """可替换风控端口（6C 可换实现）。"""

    def evaluate(
        self,
        signals: Sequence[Signal],
        targets: Sequence[TargetPosition],
        ctx: Mapping[str, Any] | None = None,
    ) -> GateResult: ...


class FiveFSignalGatePort:
    """v1：委托 production_bridge.signal_gate。"""

    def evaluate(
        self,
        signals: Sequence[Signal],
        targets: Sequence[TargetPosition],
        ctx: Mapping[str, Any] | None = None,
    ) -> GateResult:
        c = dict(ctx or {})
        return run_signal_gate(
            signals,
            targets,
            universe_membership=c.get("universe_membership"),
            max_single_weight=float(c.get("max_single_weight") or 1.0),
            max_gross_exposure=float(c.get("max_gross_exposure") or 1.0),
            max_turnover=c.get("max_turnover"),
            prev_weights=c.get("prev_weights"),
            stale_after_hours=float(c.get("stale_after_hours") or 48.0),
            now=c.get("now") if isinstance(c.get("now"), datetime) else None,
        )


class PassthroughRiskGatePort:
    """测试用：始终放行。"""

    def evaluate(
        self,
        signals: Sequence[Signal],
        targets: Sequence[TargetPosition],
        ctx: Mapping[str, Any] | None = None,
    ) -> GateResult:
        del ctx
        return GateResult(
            gate="signal",
            passed=True,
            message="passthrough",
            details={"n_signals": len(signals), "n_targets": len(targets)},
        )
