"""MAX_POSITION_DELTA：单次调整限制。"""

from __future__ import annotations

from ..protocol import RiskContext, RiskResult


class DeltaLimitRule:
    """|delta_weight| 不得超过 max_position_delta_weight。"""

    code = "MAX_POSITION_DELTA"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        lim = float(context.policy.max_position_delta_weight)
        clip = bool(context.policy.clip_on_limit)
        out: list[RiskResult] = []
        for d in context.deltas:
            dw = abs(float(d.delta_weight))
            if dw <= lim + 1e-12:
                continue
            if clip:
                sign = 1.0 if d.delta_weight >= 0 else -1.0
                new_tw = float(d.current_weight) + sign * lim
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="MODIFY",
                        message=f"clip delta {d.instrument_key} {dw:.4f}->{lim}",
                        instrument_key=d.instrument_key,
                        original_value=dw,
                        limit_value=lim,
                        adjusted_target_weight=new_tw,
                    )
                )
            else:
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="REJECT",
                        message=f"delta {d.instrument_key}={dw:.4f}>{lim}",
                        instrument_key=d.instrument_key,
                        original_value=dw,
                        limit_value=lim,
                    )
                )
        return out
