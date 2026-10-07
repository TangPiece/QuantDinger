"""DSL 规范化 + expression_hash 输入。"""

from __future__ import annotations

import re

from ..hashing import compute_expression_hash
from .lower_dsl import lower_to_dsl
from .ast import ExpressionNode


def canonicalize_dsl(dsl: str) -> str:
    """字符串级规范化（去空白、小写字段名）。"""
    text = str(dsl or "").strip()
    text = re.sub(r"\s+", "", text)
    # Ref(close,5) → ref(close,5) 字段小写
    text = re.sub(
        r"Ref\((\w+),(\d+)\)",
        lambda m: f"ref({m.group(1).lower()},{m.group(2)})",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"rolling_(mean|std)_(\d+)\((\w+)\)",
        lambda m: f"rolling_{m.group(1).lower()}_{m.group(2)}({m.group(3).lower()})",
        text,
        flags=re.I,
    )
    m = re.match(r"^(\w+)/(\w+)$", text, re.I)
    if m:
        return f"{m.group(1).lower()}/{m.group(2).lower()}"
    m = re.match(r"^(?:momentum|pct_change)_(\d+)$", text, re.I)
    if m:
        return f"momentum_{m.group(1)}"
    m = re.match(r"^volatility_(\d+)$", text, re.I)
    if m:
        return f"volatility_{m.group(1)}"
    if re.fullmatch(r"\w+", text):
        return text.lower()
    return text.lower()


def expression_hash_from_node(node: ExpressionNode) -> tuple[str, str]:
    dsl = lower_to_dsl(node)
    canon = canonicalize_dsl(dsl)
    return canon, compute_expression_hash(canon)


__all__ = ["canonicalize_dsl", "expression_hash_from_node"]
