"""FeatureAdapter：QuantDinger 表达式 → Qlib expression（Phase 2A 白名单）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.services.research_data.qlib_materializer.feature_mapper import (
    SUPPORTED_MARKET_FEATURES,
)

from .errors import UnsupportedFeatureError

# 允许的原子字段（带 $）
_ATOMIC = {f"${name}" for name in SUPPORTED_MARKET_FEATURES}

# 一元窗口算子：Op($field, n)
_WINDOW_OPS = ("Ref", "Mean", "Std", "Max", "Min", "Slope")
_WINDOW_RE = re.compile(
    r"^(Ref|Mean|Std|Max|Min|Slope)\(\s*(\$[A-Za-z_][A-Za-z0-9_]*)\s*,\s*(\d+)\s*\)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CompiledFeature:
    """一条编译后的特征。"""

    source: str
    qlib_expression: str


class FeatureAdapter:
    """将 Dataset.features / 表达式编译为 Qlib 字段列表。"""

    def compile(self, expressions: Sequence[str]) -> list[CompiledFeature]:
        """批量编译；任一非法则整体失败。"""
        out: list[CompiledFeature] = []
        for raw in expressions:
            out.append(self.compile_one(raw))
        return out

    def compile_one(self, expression: str) -> CompiledFeature:
        """编译单条表达式。

        支持：
        - $close / close
        - Ref($close, n) / Mean / Std / Max / Min / Slope
        """
        text = str(expression or "").strip()
        if not text:
            raise UnsupportedFeatureError("empty feature expression")

        # 原子字段：允许 close 或 $close
        atomic = self._normalize_atomic(text)
        if atomic is not None:
            return CompiledFeature(source=expression, qlib_expression=atomic)

        m = _WINDOW_RE.match(text)
        if m:
            op = m.group(1)
            # 规范化算子大小写
            op_norm = next(x for x in _WINDOW_OPS if x.lower() == op.lower())
            field = m.group(2)
            n = int(m.group(3))
            field_norm = self._normalize_atomic(field)
            if field_norm is None:
                raise UnsupportedFeatureError(f"unsupported field in {expression!r}")
            if n < 0:
                raise UnsupportedFeatureError(f"negative window not allowed: {expression!r}")
            qlib_expr = f"{op_norm}({field_norm}, {n})"
            return CompiledFeature(source=expression, qlib_expression=qlib_expr)

        raise UnsupportedFeatureError(
            f"unsupported feature for Phase 2A: {expression!r}; "
            f"allowed=atomic {_ATOMIC} or {_WINDOW_OPS}($field, n)"
        )

    def to_qlib_fields(self, expressions: Sequence[str]) -> list[str]:
        """返回 Qlib DataLoader 可用的 expression 列表。"""
        return [c.qlib_expression for c in self.compile(expressions)]

    @staticmethod
    def _normalize_atomic(text: str) -> str | None:
        name = text.strip()
        if name.startswith("$"):
            key = name[1:].lower()
            candidate = f"${key}"
        else:
            key = name.lower()
            candidate = f"${key}"
        if key in SUPPORTED_MARKET_FEATURES:
            return candidate
        return None
