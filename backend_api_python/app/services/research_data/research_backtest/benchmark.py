"""基准收益：NONE / INDEX / CUSTOM。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from .metrics import compute_performance
from .protocol import DailyReturnRow, NavPoint


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not hasattr(v, "hour"):
        return v
    return date.fromisoformat(str(v)[:10])


def resolve_benchmark_returns(
    calendar: Sequence[date],
    *,
    mode: str,
    instrument_key: str,
    price_index: Mapping[tuple[str, date], Mapping[str, float]],
    metadata: Mapping[str, Any] | None = None,
) -> dict[date, float]:
    """返回各交易日基准日收益（首日无收益）。"""
    meta = dict(metadata or {})
    if mode == "NONE":
        return {}
    if mode == "CUSTOM":
        raw = meta.get("benchmark_returns") or {}
        out: dict[date, float] = {}
        if isinstance(raw, Mapping):
            for k, v in raw.items():
                out[_as_date(k)] = float(v)
        return out
    # INDEX：用 close-to-close
    key = (instrument_key or "").strip()
    if not key:
        return {}
    closes: list[tuple[date, float]] = []
    for d in calendar:
        bar = price_index.get((key, d))
        if not bar:
            continue
        c = float(bar.get("close", float("nan")))
        if c == c and c > 0:
            closes.append((d, c))
    out = {}
    for i in range(1, len(closes)):
        prev_c = closes[i - 1][1]
        d, c = closes[i]
        out[d] = c / prev_c - 1.0
    return out


def attach_benchmark(
    returns: list[DailyReturnRow],
    bench_by_date: Mapping[date, float],
) -> list[DailyReturnRow]:
    """填充 benchmark_return / excess_return。"""
    out: list[DailyReturnRow] = []
    for r in returns:
        br = bench_by_date.get(r.trading_date)
        er = None
        if r.portfolio_return is not None and br is not None:
            er = float(r.portfolio_return) - float(br)
        out.append(
            r.model_copy(
                update={
                    "benchmark_return": br,
                    "excess_return": er,
                }
            )
        )
    return out


def benchmark_metrics_from_returns(
    returns: Sequence[DailyReturnRow],
    *,
    initial_nav: float = 1.0,
) -> dict[str, Any]:
    """用基准收益合成伪 NAV 再算摘要。"""
    if not returns:
        return {}
    nav_pts: list[NavPoint] = []
    nav = float(initial_nav)
    syn_returns: list[DailyReturnRow] = []
    for r in returns:
        if r.benchmark_return is not None and r.benchmark_return == r.benchmark_return:
            nav = nav * (1.0 + float(r.benchmark_return))
            syn_returns.append(
                DailyReturnRow(
                    trading_date=r.trading_date,
                    portfolio_return=float(r.benchmark_return),
                )
            )
        nav_pts.append(NavPoint(trading_date=r.trading_date, nav=nav, cash=0.0))
    if not syn_returns:
        return {}
    m = compute_performance(nav_pts, syn_returns, [], initial_nav=initial_nav)
    return m.model_dump(mode="json")


def excess_metrics(
    returns: Sequence[DailyReturnRow],
) -> dict[str, Any]:
    """超额收益均值等简要摘要。"""
    xs = [
        float(r.excess_return)
        for r in returns
        if r.excess_return is not None and r.excess_return == r.excess_return
    ]
    if not xs:
        return {}
    mean = sum(xs) / len(xs)
    return {
        "mean_excess_return": mean,
        "annualized_excess_return": mean * 252,
        "n_days": len(xs),
    }
