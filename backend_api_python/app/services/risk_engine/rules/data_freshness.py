"""DATA_FRESHNESS：行情新鲜度。"""

from __future__ import annotations

from datetime import datetime, timezone

from ..protocol import RiskContext, RiskResult


class DataFreshnessRule:
    """market_data_as_of 过旧则 REJECT。"""

    code = "DATA_FRESHNESS"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        as_of = context.market_data_as_of
        if as_of is None:
            # 未提供则跳过（Golden 可注入）
            return []
        now = context.knowledge_time or datetime.now(timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        age = (now - as_of).total_seconds()
        lim = float(context.policy.data_freshness_seconds)
        if age <= lim + 1e-9:
            return []
        return [
            RiskResult(
                rule_code=self.code,
                decision="REJECT",
                message=f"stale market data age={age:.0f}s>{lim:.0f}s",
                original_value=age,
                limit_value=lim,
            )
        ]
