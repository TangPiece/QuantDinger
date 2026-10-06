"""理论组合绩效指标（gross；年化 252）。"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

from .protocol import PortfolioReturnRow, PortfolioTurnoverRow


def _safe(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return float(v)


class PortfolioMetricsCalculator:
    """从日收益 / 换手序列汇总 AnnRet/Vol/Sharpe/MaxDD/..."""

    def calculate(
        self,
        returns: Sequence[PortfolioReturnRow],
        turnover: Sequence[PortfolioTurnoverRow],
        *,
        construction_method: str,
    ) -> dict[str, Any]:
        rets = [
            float(r.portfolio_return)
            for r in returns
            if r.portfolio_return is not None
            and not math.isnan(float(r.portfolio_return))
        ]
        metrics: dict[str, Any] = {
            "valid_day_count": len(rets),
            "total_day_count": len(returns),
        }
        if len(rets) < 2:
            metrics["annual_return"] = None
            metrics["annual_volatility"] = None
            metrics["sharpe"] = None
            metrics["max_drawdown"] = None
            metrics["calmar"] = None
        else:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            std = math.sqrt(var)
            ann_ret = mean * 252
            ann_vol = std * math.sqrt(252) if std > 0 else None
            sharpe = (mean / std * math.sqrt(252)) if std > 0 else None
            # NAV from 1.0
            nav = 1.0
            peak = 1.0
            max_dd = 0.0
            for r in rets:
                nav *= 1.0 + r
                peak = max(peak, nav)
                if peak > 0:
                    max_dd = min(max_dd, nav / peak - 1.0)
            calmar = (ann_ret / abs(max_dd)) if max_dd < 0 else None
            metrics.update(
                {
                    "annual_return": _safe(ann_ret),
                    "annual_volatility": _safe(ann_vol),
                    "sharpe": _safe(sharpe),
                    "max_drawdown": _safe(max_dd),
                    "calmar": _safe(calmar),
                }
            )

        wins = [r for r in rets if r > 0]
        metrics["win_rate"] = (len(wins) / len(rets)) if rets else None

        to_vals = [
            float(t.turnover)
            for t in turnover
            if t.turnover is not None and not math.isnan(float(t.turnover))
        ]
        metrics["mean_turnover"] = (
            sum(to_vals) / len(to_vals) if to_vals else None
        )

        if construction_method in ("LONG_SHORT", "QUANTILE"):
            longs = [
                float(r.long_return)
                for r in returns
                if r.long_return is not None
            ]
            shorts = [
                float(r.short_return)
                for r in returns
                if r.short_return is not None
            ]
            ls = [
                float(r.long_short_return)
                for r in returns
                if r.long_short_return is not None
            ]
            metrics["mean_long_return"] = (
                sum(longs) / len(longs) if longs else None
            )
            metrics["mean_short_return"] = (
                sum(shorts) / len(shorts) if shorts else None
            )
            metrics["mean_long_short_return"] = (
                sum(ls) / len(ls) if ls else None
            )
        return metrics
