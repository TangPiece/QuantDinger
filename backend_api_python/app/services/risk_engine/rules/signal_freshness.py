"""SIGNAL_FRESHNESS：信号 TTL。"""

from __future__ import annotations

from datetime import datetime, timezone

from ..protocol import RiskContext, RiskResult


class SignalFreshnessRule:
    """Signal.knowledge_time / timestamp 过旧则 REJECT。"""

    code = "SIGNAL_FRESHNESS"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        if not context.signals:
            return []
        now = context.knowledge_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        lim = float(context.policy.signal_ttl_seconds)
        out: list[RiskResult] = []
        for s in context.signals:
            kt = getattr(s, "knowledge_time", None) or getattr(s, "signal_time", None)
            if kt is None:
                continue
            if kt.tzinfo is None:
                kt = kt.replace(tzinfo=timezone.utc)
            age = (now - kt).total_seconds()
            if age > lim + 1e-9:
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="REJECT",
                        message=f"stale signal {getattr(s, 'instrument_key', '')} age={age:.0f}s",
                        instrument_key=str(getattr(s, "instrument_key", "") or ""),
                        original_value=age,
                        limit_value=lim,
                    )
                )
                break
        return out
