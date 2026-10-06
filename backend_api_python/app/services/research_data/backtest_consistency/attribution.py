"""Level 0→5 Production 政策阶梯归因。"""

from __future__ import annotations

from typing import Callable, Mapping

from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.backtest.request import BacktestRequest
from app.services.research_data.backtest.result import BacktestResult
from app.services.research_data.contracts import TargetPosition

from .levels import LEVEL_ORDER, LEVEL_STEP_COMPONENT, policies_for_level
from .models import ConsistencyAttribution, ConsistencyLevel


def _final_equity(result: BacktestResult, initial: float) -> float:
    if result.equity_curve:
        return float(result.equity_curve[-1].equity)
    return float(initial)


def _return_vs_initial(equity: float, initial: float) -> float:
    if initial <= 0:
        return 0.0
    return (equity / initial) - 1.0


def attribute_level_ladder(
    *,
    base_request: BacktestRequest,
    run_production: Callable[..., BacktestResult],
    bars_by_date: Mapping[str, Mapping[str, MarketBar]] | None = None,
    targets_by_date: dict[str, list[TargetPosition]] | None = None,
    up_to_level: ConsistencyLevel = "L5",
    rejected_reasons: list[str] | None = None,
) -> list[ConsistencyAttribution]:
    """对 Production 从 L0 逐步加严，用相邻层收益差做归因。

    Args:
        run_production: ``(request, bars_by_date=, targets_by_date=) -> BacktestResult``
        up_to_level: 阶梯上限
        rejected_reasons: L5 拒单原因，用于拆 limit/suspend/cash
    """
    stop = LEVEL_ORDER.index(up_to_level)
    levels = LEVEL_ORDER[: stop + 1]
    equities: dict[str, float] = {}
    initial = float(base_request.initial_capital)

    for lvl in levels:
        exec_p, price_p, cost_p, rules = policies_for_level(lvl)
        req = base_request.model_copy(
            update={
                "engine": "production",
                "execution_policy": exec_p,
                "market_price_policy": price_p,
                "cost_policy": cost_p,
                "trading_rule": rules,
            }
        )
        res = run_production(
            req,
            bars_by_date=bars_by_date,
            targets_by_date=targets_by_date,
        )
        equities[lvl] = _final_equity(res, initial)

    attrs: list[ConsistencyAttribution] = []
    for i in range(1, len(levels)):
        prev, curr = levels[i - 1], levels[i]
        impact = _return_vs_initial(equities[curr], initial) - _return_vs_initial(
            equities[prev], initial
        )
        component = LEVEL_STEP_COMPONENT.get(curr, "other")
        attrs.append(
            ConsistencyAttribution(
                component=component,  # type: ignore[arg-type]
                return_impact=float(impact),
                notes=f"{prev}->{curr} equity {equities[prev]:.6f}->{equities[curr]:.6f}",
            )
        )

    # L5：按拒单原因拆细（从 limit 桶再分配，总和必须不变）
    if up_to_level == "L5" and rejected_reasons:
        limit_idx = next(
            (i for i, a in enumerate(attrs) if a.component == "limit"), None
        )
        if limit_idx is not None:
            bucket = attrs[limit_idx].return_impact
            counts = {"limit": 0, "suspend": 0, "cash": 0}
            for r in rejected_reasons:
                if r in ("LIMIT_UP", "LIMIT_DOWN"):
                    counts["limit"] += 1
                elif r == "SUSPENDED":
                    counts["suspend"] += 1
                elif r == "INSUFFICIENT_CASH":
                    counts["cash"] += 1
            total = sum(counts.values())
            attrs.pop(limit_idx)
            if total <= 0:
                # 无限制类拒单（如仅 LOT）：保留整桶，避免归因丢失 → Unknown residual
                attrs.append(
                    ConsistencyAttribution(
                        component="limit",
                        return_impact=float(bucket),
                        notes="L5 aggregate (no limit/suspend/cash rejects)",
                    )
                )
            else:
                for comp, n in counts.items():
                    if n <= 0:
                        continue
                    attrs.append(
                        ConsistencyAttribution(
                            component=comp,  # type: ignore[arg-type]
                            return_impact=float(bucket * n / total),
                            notes=f"L5 reject share {comp}={n}/{total}",
                        )
                    )

    # other：相对 L0→终点 未解释残差（阶梯应闭合，正常≈0）
    if len(levels) >= 2:
        total_ladder = sum(a.return_impact for a in attrs)
        observed = _return_vs_initial(equities[levels[-1]], initial) - _return_vs_initial(
            equities[levels[0]], initial
        )
        other = observed - total_ladder
        attrs.append(
            ConsistencyAttribution(
                component="other",
                return_impact=float(other),
                notes="ladder residual",
            )
        )
    return attrs


def qlib_vs_prod_gap(
    qlib_result: BacktestResult | None,
    prod_result: BacktestResult,
    initial_capital: float,
) -> float | None:
    """Qlib 与 Production 总收益差（prod - qlib）。"""
    if qlib_result is None or not qlib_result.equity_curve:
        return None
    q = _final_equity(qlib_result, initial_capital)
    p = _final_equity(prod_result, initial_capital)
    return _return_vs_initial(p, initial_capital) - _return_vs_initial(q, initial_capital)
