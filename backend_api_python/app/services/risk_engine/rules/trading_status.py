"""TradingStatus：停牌 / 涨跌停。"""

from __future__ import annotations

from ..protocol import RiskContext, RiskResult


class TradingStatusRule:
    """停牌禁交易；涨停禁买；跌停禁卖。"""

    code = "TRADING_STATUS"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        status = context.trading_status or {}
        if not status:
            return []
        out: list[RiskResult] = []
        for d in context.deltas:
            if d.side == "FLAT" or abs(float(d.delta_quantity)) < 1e-12:
                continue
            row = status.get(d.instrument_key) or {}
            if row.get("is_suspended") or str(row.get("status") or "").upper() in {
                "SUSPENDED",
                "HALT",
            }:
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="REJECT",
                        message=f"suspended {d.instrument_key}",
                        instrument_key=d.instrument_key,
                        metadata={"reason": "SUSPENDED"},
                    )
                )
                continue
            if d.side == "BUY" and row.get("is_limit_up"):
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="REJECT",
                        message=f"limit_up ban buy {d.instrument_key}",
                        instrument_key=d.instrument_key,
                        metadata={"reason": "LIMIT_UP"},
                    )
                )
            if d.side == "SELL" and row.get("is_limit_down"):
                out.append(
                    RiskResult(
                        rule_code=self.code,
                        decision="REJECT",
                        message=f"limit_down ban sell {d.instrument_key}",
                        instrument_key=d.instrument_key,
                        metadata={"reason": "LIMIT_DOWN"},
                    )
                )
        return out
