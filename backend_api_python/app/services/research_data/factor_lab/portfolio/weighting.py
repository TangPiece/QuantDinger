"""EQUAL / SCORE / RANK 权重生成（选定集合内归一化）。"""

from __future__ import annotations

import math
from typing import Sequence


def _average_ranks(values: list[float]) -> list[float]:
    """平均秩（ties）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def allocate_weights(
    scores: Sequence[float],
    *,
    method: str,
    sign: float = 1.0,
) -> list[float]:
    """在选定集合内分配权重；sign=+1 多头（和=sign），sign=-1 空头（和=sign）。"""
    n = len(scores)
    if n == 0:
        return []
    target = float(sign)

    if method == "EQUAL_WEIGHT":
        w = target / n
        return [w] * n

    if method == "SCORE_WEIGHT":
        if sign >= 0:
            raw = [max(float(s), 0.0) for s in scores]
        else:
            raw = [max(-float(s), 0.0) for s in scores]
        ssum = sum(raw)
        if ssum <= 0.0 or any(math.isnan(x) for x in raw):
            w = target / n
            return [w] * n
        return [target * (x / ssum) for x in raw]

    if method == "RANK_WEIGHT":
        ranks = _average_ranks([float(s) for s in scores])
        # 空头侧对 factor 分数取负后选股，此处 rank 仍按传入 scores 计算
        if sign < 0:
            # 短端：更低分应更大 |权重| → 用反向 rank
            ranks = [n + 1.0 - r for r in ranks]
        ssum = sum(ranks)
        if ssum <= 0:
            w = target / n
            return [w] * n
        return [target * (r / ssum) for r in ranks]

    raise ValueError(f"unknown weight_method={method!r}")
