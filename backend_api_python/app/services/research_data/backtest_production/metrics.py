"""从权益曲线 / 成交计算 BacktestMetrics（与 Portfolio 账本分离）。"""

from __future__ import annotations

import math
from typing import Sequence

from app.services.research_data.backtest.ledger import EquityPoint, TradeRecord
from app.services.research_data.backtest.result import BacktestMetrics


def _safe(value: float | None) -> float | None:
    if value is None:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def compute_metrics(
    equity_curve: Sequence[EquityPoint],
    *,
    trades: Sequence[TradeRecord] | None = None,
    initial_capital: float | None = None,
) -> BacktestMetrics:
    """日频权益指标；数据不足时对应字段为 None。"""
    if not equity_curve:
        return BacktestMetrics()

    equities = [float(p.equity) for p in equity_curve]
    start = float(initial_capital) if initial_capital is not None else equities[0]
    if start <= 0:
        start = equities[0] if equities[0] else 1.0

    total_return = equities[-1] / start - 1.0 if start else None
    if len(equities) < 2:
        return BacktestMetrics(total_return=_safe(total_return))

    rets = []
    for i in range(1, len(equities)):
        prev = equities[i - 1]
        if prev > 0:
            rets.append(equities[i] / prev - 1.0)

    if not rets:
        return BacktestMetrics(total_return=_safe(total_return))

    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
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

    downside = [r for r in rets if r < 0]
    sortino = None
    if downside:
        dstd = math.sqrt(sum(r * r for r in downside) / len(downside))
        if dstd > 0:
            sortino = mean / dstd * math.sqrt(252)

    calmar = None
    if max_dd < 0:
        calmar = annualized / abs(max_dd)

    turnover = None
    if trades:
        filled = [t for t in trades if t.status in ("FILLED", "PARTIAL") and t.quantity > 0]
        if filled and start > 0:
            notional = sum(
                abs(float(t.quantity) * float(t.executed_price or 0.0)) for t in filled
            )
            turnover = notional / start / max(len(equities), 1)

    win_rate = None
    profit_factor = None
    # 简化：用正收益日占比
    if rets:
        wins = sum(1 for r in rets if r > 0)
        win_rate = wins / len(rets)
        gain = sum(r for r in rets if r > 0)
        loss = -sum(r for r in rets if r < 0)
        if loss > 0:
            profit_factor = gain / loss

    return BacktestMetrics(
        total_return=_safe(total_return),
        annualized_return=_safe(annualized),
        volatility=_safe(vol),
        sharpe=_safe(sharpe),
        sortino=_safe(sortino),
        max_drawdown=_safe(max_dd),
        calmar=_safe(calmar),
        turnover=_safe(turnover),
        win_rate=_safe(win_rate),
        profit_factor=_safe(profit_factor),
    )


def attach_drawdown(equity_curve: list[EquityPoint]) -> list[EquityPoint]:
    """就地填写 drawdown 字段。"""
    if not equity_curve:
        return equity_curve
    peak = equity_curve[0].equity
    out: list[EquityPoint] = []
    for p in equity_curve:
        peak = max(peak, p.equity)
        dd = (p.equity / peak - 1.0) if peak > 0 else 0.0
        out.append(p.model_copy(update={"drawdown": dd}))
    return out
