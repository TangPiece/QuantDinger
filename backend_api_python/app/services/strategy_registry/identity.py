"""Phase 8A：strategy_code 规范化；strategy_id 与规范化 code 等价。"""

from __future__ import annotations

import re

# 与 7E golden / 5A 研究策略命名对齐：小写字母开头，后续字母数字 _ -
_STRATEGY_CODE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")


class InvalidStrategyIdentityError(ValueError):
    """非法 strategy_code / strategy_id。"""


def normalize_strategy_code(raw: str) -> str:
    """将用户输入规范为 SSOT strategy_code（亦即 strategy_id）。"""
    text = str(raw or "").strip().lower()
    text = re.sub(r"[\s.]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text or not _STRATEGY_CODE_RE.match(text):
        raise InvalidStrategyIdentityError(
            f"invalid strategy_code: {raw!r}; expect ^[a-z][a-z0-9_-]{{1,62}}$"
        )
    return text


def strategy_id_from_code(strategy_code: str) -> str:
    """strategy_id ≡ normalized strategy_code。"""
    return normalize_strategy_code(strategy_code)
