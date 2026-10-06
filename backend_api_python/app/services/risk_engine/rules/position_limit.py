"""MAX_SINGLE_POSITION：单标的最大仓位。"""

from __future__ import annotations

from ..protocol import RiskContext, RiskResult


class PositionLimitRule:
    """单票目标权重不得超过 max_single_position_weight。"""

    code = "MAX_SINGLE_POSITION"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        lim = float(context.policy.max_single_position_weight)
        clip = bool(context.policy.clip_on_limit)
        out: list[RiskResult] = []
        for d in context.deltas:
            tw = abs(float(d.target_weight))
            if tw <= lim + 1e-12:
                continue
            if clip:
                sign = 1.0 if d.target_weight >= 0 else -1.0
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="MODIFY",
                        message=f"clip single position {d.instrument_key} {tw:.4f}->{lim}",
                        instrument_key=d.instrument_key,
                        original_value=tw,
                        limit_value=lim,
                        adjusted_target_weight=sign * lim,
                    )
                )
            else:
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="REJECT",
                        message=f"single position {d.instrument_key}={tw:.4f}>{lim}",
                        instrument_key=d.instrument_key,
                        original_value=tw,
                        limit_value=lim,
                    )
                )
        return out
