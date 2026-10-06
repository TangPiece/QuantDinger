"""研究回测绩效（对齐 3D 生产引擎的 252 日年化公式，独立实现）。"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from .protocol import DailyReturnRow, NavPoint, PerformanceMetrics, TurnoverRow


def _safe(value: float | None) -> float | None:
    if value is None:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def compute_performance(
    nav: Sequence[NavPoint],
    returns: Sequence[DailyReturnRow],
    turnover: Sequence[TurnoverRow],
    *,
    initial_nav: float,
) -> PerformanceMetrics:
    """从 NAV / 日收益 / 换手计算摘要指标。"""
    if not nav:
        return PerformanceMetrics()

    equities = [float(p.nav) for p in nav]
    start = float(initial_nav) if initial_nav > 0 else equities[0]
    total_return = equities[-1] / start - 1.0 if start else None

    rets = [
        float(r.portfolio_return)
        for r in returns
        if r.portfolio_return is not None
        and r.portfolio_return == r.portfolio_return
    ]
    if not rets:
        return PerformanceMetrics(
            total_return=_safe(total_return),
            n_days=len(nav),
            n_rebalances=sum(1 for t in turnover if t.rebalanced),
        )

    mean = sum(rets) / len(rets)
    var = (
        sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    )
    std = math.sqrt(var)
    annualized = mean * 252
    vol = std * math.sqrt(252) if std > 0 else None
    sharpe = (mean / std * math.sqrt(252)) if std > 0 else None

    peak = equities[0]
    max_dd = 0.0
    for e in equities:
        peak = max(peak, e)
        if peak > 0:
            max_dd = min(max_dd, e / peak - 1.0)

    calmar: Optional[float] = None
    if max_dd < 0:
        calmar = annualized / abs(max_dd)

    win_rate = sum(1 for r in rets if r > 0) / len(rets) if rets else None
    turn_vals = [
        float(t.turnover)
        for t in turnover
        if t.rebalanced and t.turnover is not None and t.turnover == t.turnover
    ]
    mean_to = sum(turn_vals) / len(turn_vals) if turn_vals else None

    return PerformanceMetrics(
        total_return=_safe(total_return),
        annualized_return=_safe(annualized),
        annualized_volatility=_safe(vol),
        sharpe=_safe(sharpe),
        max_drawdown=_safe(max_dd),
        calmar=_safe(calmar),
        win_rate=_safe(win_rate),
        mean_turnover=_safe(mean_to),
        n_days=len(nav),
        n_rebalances=sum(1 for t in turnover if t.rebalanced),
    )
