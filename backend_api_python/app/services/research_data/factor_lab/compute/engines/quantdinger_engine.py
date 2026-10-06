"""QuantDinger 引擎：委托 PolarsFactorEngine。"""

from __future__ import annotations

from app.services.research_data.factor_lab.compute.protocol import ComputePlan, FactorFrame

from .polars_engine import PolarsFactorEngine


class QuantDingerFactorEngine:
    """默认研究引擎别名 → Polars 实现。"""

    name = "quantdinger"

    def __init__(self) -> None:
        self._inner = PolarsFactorEngine()

    def supports(self, factor, plan: ComputePlan) -> bool:
        return plan.engine == "quantdinger"

    def compute(self, plan: ComputePlan, *, query, registry) -> FactorFrame:
        return self._inner.compute(plan, query=query, registry=registry)
