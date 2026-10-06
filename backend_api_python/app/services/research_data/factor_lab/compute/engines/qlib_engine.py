"""Qlib 薄适配：表达式经 FeatureAdapter 语义对齐，数值用 pandas DSL（无 Domain 持有 qlib 对象）。

缺 pyqlib 时 ``supports`` 仍可为 True，但 ``compute`` 回退到与 FeatureAdapter 等价的 pandas 路径，
保证 CI 可跑；真正调用 qlib 时仅用于校验 import。
"""

from __future__ import annotations

from datetime import date

from app.services.research_data.factor_lab.compute.dsl import evaluate_on_market, frame_to_long_records
from app.services.research_data.factor_lab.compute.protocol import ComputePlan, FactorFrame


class QlibFactorEngine:
    """Qlib-compatible daily expressions → FactorFrame。"""

    name = "qlib"

    def supports(self, factor, plan: ComputePlan) -> bool:
        return plan.engine == "qlib"

    def compute(self, plan: ComputePlan, *, query, registry) -> FactorFrame:
        # 可选：确认 qlib 可导入（不把类型带入 Domain）
        try:
            import qlib  # noqa: F401
        except Exception:
            pass

        # 将 $close / Ref($close,n) 映射为 DSL
        expr = self._to_dsl(plan.expression)
        code, version = plan.factor_ref.split("@", 1)
        meta = plan.metadata or {}
        instruments = list(meta.get("instruments") or meta.get("instrument_keys") or [])
        start = date.fromisoformat(plan.start_date[:10])
        end = date.fromisoformat(plan.end_date[:10])
        market = query.market(
            instruments,
            start,
            end,
            frequency="1d",
            price_policy=plan.price_policy,
            exchange=meta.get("exchange", "CN"),
        )
        if market is None or market.empty:
            return FactorFrame.from_records([])
        values = evaluate_on_market(market, expr)
        records = frame_to_long_records(
            market, values, factor_code=code, factor_version=version
        )
        return FactorFrame.from_records(records, layout="long")

    @staticmethod
    def _to_dsl(expression: str) -> str:
        text = (expression or "").strip()
        # Ref($close, 20) → Ref(close, 20)
        text = text.replace("$", "")
        # Momentum 常用：close/Ref(close,20)-1 简化为 momentum_20
        import re

        m = re.match(
            r"^close\s*/\s*Ref\(\s*close\s*,\s*(\d+)\s*\)\s*-\s*1$",
            text,
            re.I,
        )
        if m:
            return f"momentum_{m.group(1)}"
        return text
