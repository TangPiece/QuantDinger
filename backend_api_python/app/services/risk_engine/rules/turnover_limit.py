"""MAX_TURNOVER：最大换手。"""

from __future__ import annotations

from ..protocol import RiskContext, RiskResult


class TurnoverLimitRule:
    """0.5 * sum(|delta_weight|) 不得超过 max_turnover。"""

    code = "MAX_TURNOVER"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        lim = float(context.policy.max_turnover)
        turnover = 0.5 * sum(abs(float(d.delta_weight)) for d in context.deltas)
        if turnover <= lim + 1e-12:
            return []
        clip = bool(context.policy.clip_on_limit)
        if not clip:
            return [
                RiskResult(
                    rule_code=self.code,
                    decision="REJECT",
                    message=f"turnover {turnover:.4f}>{lim}",
                    original_value=turnover,
                    limit_value=lim,
                )
            ]
        scale = (2.0 * lim) / sum(abs(float(d.delta_weight)) for d in context.deltas)
        out: list[RiskResult] = []
        for d in context.deltas:
            # 向 current 回撤：new_target = current + scale * delta
            new_tw = float(d.current_weight) + scale * float(d.delta_weight)
            out.append(
                RiskResult(
                    rule_code=self.code,
                    decision="MODIFY",
                    severity="P1",
                    message=f"clip turnover {turnover:.4f}->{lim}",
                    instrument_key=d.instrument_key,
                    original_value=turnover,
                    limit_value=lim,
                    adjusted_target_weight=new_tw,
                    metadata={"scale": scale},
                )
            )
        return out
