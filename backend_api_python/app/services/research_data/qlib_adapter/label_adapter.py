"""LabelAdapter：未来收益 / 负向 Ref（仅 Label 路径；Feature 禁止）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.research_data.contracts import LabelDefinition

from .errors import UnsupportedFeatureError
from .specs import default_fwd_ret_label

# Ref($close, -5) / $close - 1
_FWD_RET_RE = re.compile(
    r"^Ref\(\s*(\$[A-Za-z_][A-Za-z0-9_]*)\s*,\s*(-\d+)\s*\)\s*/\s*"
    r"(\$[A-Za-z_][A-Za-z0-9_]*)\s*-\s*1$",
    re.IGNORECASE,
)
# 单独负向 Ref($close, -5)
_NEG_REF_RE = re.compile(
    r"^Ref\(\s*(\$[A-Za-z_][A-Za-z0-9_]*)\s*,\s*(-\d+)\s*\)$",
    re.IGNORECASE,
)
_ALLOWED_FIELDS = frozenset({"$open", "$high", "$low", "$close", "$volume", "$amount", "$vwap"})


@dataclass(frozen=True)
class CompiledLabel:
    """编译后的 Label 表达式。"""

    source: str
    qlib_expression: str
    horizon: int


class LabelAdapter:
    """编译 LabelDefinition → Qlib label expression。"""

    def resolve(
        self,
        label: LabelDefinition | None,
        *,
        fallback_horizon: int = 5,
    ) -> tuple[LabelDefinition, CompiledLabel]:
        """解析 label；空则用默认 fwd_ret。"""
        definition = label or default_fwd_ret_label(horizon=fallback_horizon)
        compiled = self.compile(definition)
        return definition, compiled

    def compile(self, label: LabelDefinition) -> CompiledLabel:
        """编译单条 Label；只允许负向 Ref / 未来收益式。"""
        text = str(label.expression or "").strip()
        if not text:
            raise UnsupportedFeatureError("empty label expression")

        m = _FWD_RET_RE.match(text)
        if m:
            field_a = m.group(1).lower()
            lag = int(m.group(2))
            field_b = m.group(3).lower()
            if field_a not in _ALLOWED_FIELDS or field_b not in _ALLOWED_FIELDS:
                raise UnsupportedFeatureError(f"unsupported label field in {text!r}")
            if lag >= 0:
                raise UnsupportedFeatureError(f"label Ref lag must be negative: {text!r}")
            horizon = abs(lag)
            expr = f"Ref({field_a}, {lag}) / {field_b} - 1"
            return CompiledLabel(source=label.expression, qlib_expression=expr, horizon=horizon)

        m2 = _NEG_REF_RE.match(text)
        if m2:
            field = m2.group(1).lower()
            lag = int(m2.group(2))
            if field not in _ALLOWED_FIELDS:
                raise UnsupportedFeatureError(f"unsupported label field in {text!r}")
            if lag >= 0:
                raise UnsupportedFeatureError(f"label Ref lag must be negative: {text!r}")
            return CompiledLabel(
                source=label.expression,
                qlib_expression=f"Ref({field}, {lag})",
                horizon=abs(lag),
            )

        raise UnsupportedFeatureError(
            f"unsupported label for Phase 2B: {text!r}; "
            "allowed=Ref($close,-N)/$close-1 or Ref($close,-N)"
        )
