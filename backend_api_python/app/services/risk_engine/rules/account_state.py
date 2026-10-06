"""ACCOUNT_STATE：账户可交易 / 现金 / 可卖数量 / 禁止卖空。"""

from __future__ import annotations

from ..protocol import RiskContext, RiskResult


class AccountStateRule:
    """ACTIVE only；BUY 需足够 available_cash；SELL 需 available_quantity；默认禁卖空。"""

    code = "ACCOUNT_STATE"

    def evaluate(self, context: RiskContext) -> list[RiskResult]:
        out: list[RiskResult] = []
        acct = context.account
        if acct is None:
            return [
                RiskResult(
                    rule_code=self.code,
                    decision="REJECT",
                    message="account missing",
                )
            ]
        if str(acct.status) != "ACTIVE":
            out.append(
                RiskResult(
                    rule_code=self.code,
                    decision="REJECT",
                    message=f"account status={acct.status}",
                    original_value=0.0,
                    limit_value=0.0,
                    metadata={"status": acct.status},
                )
            )
            return out

        cash = float(acct.cash.available_cash)
        buy_notional = 0.0
        for d in context.deltas:
            if d.side == "BUY" and float(d.delta_quantity) > 0:
                px = float(context.prices.get(d.instrument_key) or 0.0)
                buy_notional += abs(float(d.delta_quantity)) * px
            if d.side == "SELL":
                pos = context.positions.get(d.instrument_key)
                avail = float(pos.available_quantity) if pos else 0.0
                need = abs(float(d.delta_quantity))
                if need > avail + 1e-9:
                    if not context.policy.short_allowed:
                        out.append(
                            RiskResult(
                                rule_code=self.code,
                                decision="REJECT",
                                message=(
                                    f"insufficient available qty {d.instrument_key}: "
                                    f"need {need}, have {avail}"
                                ),
                                instrument_key=d.instrument_key,
                                original_value=need,
                                limit_value=avail,
                            )
                        )
                # 卖空：目标数量为负
                target_q = float(d.target_quantity)
                if target_q < -1e-9 and not context.policy.short_allowed:
                    out.append(
                        RiskResult(
                            rule_code=self.code,
                            decision="REJECT",
                            message=f"short not allowed {d.instrument_key}",
                            instrument_key=d.instrument_key,
                            original_value=target_q,
                            limit_value=0.0,
                        )
                    )

        if buy_notional > cash + 1e-6:
            out.append(
                RiskResult(
                    rule_code=self.code,
                    decision="REJECT",
                    message=f"insufficient cash need={buy_notional:.2f} have={cash:.2f}",
                    original_value=buy_notional,
                    limit_value=cash,
                )
            )
        return out
