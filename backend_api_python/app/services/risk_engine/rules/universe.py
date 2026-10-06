"""UNIVERSE：标的必须在 membership。"""

from __future__ import annotations

from ..protocol import RiskContext, RiskResult


class UniverseRule:
    """目标/调仓标的须属于 universe_membership（require_universe 或名单非空）。"""

    code = "UNIVERSE"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        membership = {str(x) for x in (context.policy.universe_membership or [])}
        if not membership and not context.policy.require_universe:
            return []
        if context.policy.require_universe and not membership:
            return [
                RiskResult(
                    rule_code=self.code,
                    decision="REJECT",
                    message="universe required but empty",
                )
            ]
        out: list[RiskResult] = []
        for d in context.deltas:
            if abs(float(d.delta_quantity)) < 1e-12 and d.side == "FLAT":
                continue
            if d.instrument_key not in membership:
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="REJECT",
                        message=f"outside universe {d.instrument_key}",
                        instrument_key=d.instrument_key,
                    )
                )
        return out
