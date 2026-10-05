"""QuantDingerWeightStrategy：按日跟随 TargetPosition 权重调仓。

不重写 TopK；权重已由 Signal 层确定。缺省日不调仓；全日权重为 0 则清空持仓。
"""

from __future__ import annotations

import copy
from typing import Any

import pandas as pd

from .signal_loader import weights_for_date


class QuantDingerWeightStrategy:
    """懒加载包装：真正的 Qlib BaseStrategy 子类在首次实例化时定义。

    这样 ``backtest/`` 包的 AST 约束测试不会被间接 import 污染；
    仅在 ``backtest_qlib`` 运行时才依赖 pyqlib。
    """

    def __new__(cls, *args: Any, **kwargs: Any):
        return _build_strategy_class()(*args, **kwargs)


def _build_strategy_class():
    """构造继承 qlib.strategy.base.BaseStrategy 的真实策略类。"""
    from qlib.backtest.decision import TradeDecisionWO
    from qlib.backtest.position import Position
    from qlib.contrib.strategy.order_generator import OrderGenWInteract
    from qlib.strategy.base import BaseStrategy

    class _QuantDingerWeightStrategy(BaseStrategy):
        """按日读目标权重，经 OrderGenWInteract 生成调仓单。"""

        def __init__(
            self,
            *,
            target_weights: pd.Series,
            risk_degree: float = 1.0,
            order_generator=None,
            **kwargs: Any,
        ) -> None:
            """
            Args:
                target_weights: MultiIndex (datetime, instrument) → weight
                risk_degree: 投入总资产比例（默认 1.0，权重已由 Signal 归一）
                order_generator: 默认 OrderGenWInteract（T+0 close 研究路径）
            """
            super().__init__(**kwargs)
            self.target_weights = target_weights
            self.risk_degree = float(risk_degree)
            self.order_generator = order_generator or OrderGenWInteract()
            # 缓存最近一次调仓日权重，供验收对齐
            self.last_target_weights: dict[str, float] | None = None

        def get_risk_degree(self, trade_step=None) -> float:
            return self.risk_degree

        def generate_trade_decision(self, execute_result=None):
            trade_step = self.trade_calendar.get_trade_step()
            trade_start_time, trade_end_time = self.trade_calendar.get_step_time(trade_step)
            # 预测窗取上一日，供 OrderGen 估量价；权重锚定本交易日
            pred_start_time, pred_end_time = self.trade_calendar.get_step_time(
                trade_step, shift=1
            )

            day_weights = weights_for_date(self.target_weights, trade_start_time)
            if day_weights is None:
                # 缺省日：不调仓
                self.last_target_weights = None
                return TradeDecisionWO([], self)

            # 权重全 0 → 空 dict，OrderGen 会清空可交易仓位
            if day_weights and all(abs(v) < 1e-12 for v in day_weights.values()):
                target_weight_position: dict[str, float] = {}
            else:
                target_weight_position = {
                    k: float(v) for k, v in day_weights.items() if abs(v) >= 1e-12
                }

            self.last_target_weights = dict(target_weight_position)
            current_temp = copy.deepcopy(self.trade_position)
            if not isinstance(current_temp, Position):
                return TradeDecisionWO([], self)

            order_list = self.order_generator.generate_order_list_from_target_weight_position(
                current=current_temp,
                trade_exchange=self.trade_exchange,
                risk_degree=self.get_risk_degree(trade_step),
                target_weight_position=target_weight_position,
                pred_start_time=pred_start_time,
                pred_end_time=pred_end_time,
                trade_start_time=trade_start_time,
                trade_end_time=trade_end_time,
            )
            return TradeDecisionWO(order_list, self)

    _QuantDingerWeightStrategy.__name__ = "QuantDingerWeightStrategy"
    _QuantDingerWeightStrategy.__qualname__ = "QuantDingerWeightStrategy"
    return _QuantDingerWeightStrategy
