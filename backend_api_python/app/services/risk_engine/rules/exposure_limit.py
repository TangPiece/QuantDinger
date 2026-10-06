"""MAX_GROSS_EXPOSURE：总仓位。"""

from __future__ import annotations

from ..protocol import RiskContext, RiskResult


class ExposureLimitRule:
    """目标毛敞口（按 |target_weight| 之和）不得超过上限。"""

    code = "MAX_GROSS_EXPOSURE"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        lim = float(context.policy.max_gross_exposure)
        # 用 delta 的 target_weight 汇总；无则用 exposure
        gross = sum(abs(float(d.target_weight)) for d in context.deltas)
        if not context.deltas and context.exposure:
            gross = float(context.exposure.gross_exposure)
            if context.equity > 0:
                gross = gross / float(context.equity)
        if gross <= lim + 1e-12:
            return []
        clip = bool(context.policy.clip_on_limit)
        if not clip:
            return [
                RiskResult(
                    rule_code=self.code,
                    decision="REJECT",
                    message=f"gross exposure {gross:.4f}>{lim}",
                    original_value=gross,
                    limit_value=lim,
                )
            ]
        # 等比缩放到 lim
        scale = lim / gross if gross > 0 else 0.0
        out: list[RiskResult] = []
        for d in context.deltas:
            tw = float(d.target_weight) * scale
            out.append(
                RiskResult(
                    rule_code=self.code,
                    decision="MODIFY",
                    message=f"scale gross {gross:.4f}->{lim}",
                    instrument_key=d.instrument_key,
                    original_value=float(d.target_weight),
                    limit_value=lim,
                    adjusted_target_weight=tw,
                    metadata={"scale": scale},
                )
            )
        if not out:
            out.append(
                RiskResult(
                    rule_code=self.code,
                    decision="MODIFY",
                    message=f"scale gross {gross:.4f}->{lim}",
                    original_value=gross,
                    limit_value=lim,
                    metadata={"scale": scale},
                )
            )
        return out
