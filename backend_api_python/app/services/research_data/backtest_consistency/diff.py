"""BacktestResult 逐维 Diff（equity / position / trade / cost / cash / rejected）。"""

from __future__ import annotations

from app.services.research_data.backtest.execution.models import (
    REASON_INSUFFICIENT_CASH,
    REASON_LIMIT_DOWN,
    REASON_LIMIT_UP,
    REASON_LOT_SIZE_FLOOR,
    REASON_LOT_SIZE_REJECT,
    REASON_SUSPENDED,
    REASON_T_PLUS,
)
from app.services.research_data.backtest.result import BacktestResult

from .models import ConsistencyDiff

# L5 允许的已解释原因（禁止 Unknown）
KNOWN_DIFF_REASONS: frozenset[str] = frozenset(
    {
        REASON_T_PLUS,
        REASON_LIMIT_UP,
        REASON_LIMIT_DOWN,
        REASON_SUSPENDED,
        REASON_LOT_SIZE_FLOOR,
        REASON_LOT_SIZE_REJECT,
        REASON_INSUFFICIENT_CASH,
        "EXECUTION_DELAY",
        "COMMISSION",
        "SLIPPAGE",
        "ENGINE_SEMANTICS",
        "QLIB_ABSENT",
        "FLOAT_TOLERANCE",
        "OK",
    }
)


def _rel(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    denom = max(abs(a), abs(b), 1e-12)
    return (b - a) / denom


def compare_equity(
    qlib: BacktestResult | None,
    prod: BacktestResult,
    *,
    tolerance: float = 1e-6,
) -> list[ConsistencyDiff]:
    """按交易日对齐权益曲线。"""
    q_map = {
        p.trading_date: float(p.equity)
        for p in (qlib.equity_curve if qlib else [])
    }
    diffs: list[ConsistencyDiff] = []
    for p in prod.equity_curve:
        qv = q_map.get(p.trading_date)
        pv = float(p.equity)
        if qv is None:
            if qlib is None:
                continue
            diffs.append(
                ConsistencyDiff(
                    dimension="equity",
                    trading_date=p.trading_date,
                    qlib_value=None,
                    quantdinger_value=pv,
                    absolute_diff=None,
                    reason="ENGINE_SEMANTICS",
                )
            )
            continue
        ad = pv - qv
        if abs(ad) <= tolerance:
            continue
        diffs.append(
            ConsistencyDiff(
                dimension="equity",
                trading_date=p.trading_date,
                qlib_value=qv,
                quantdinger_value=pv,
                absolute_diff=ad,
                relative_diff=_rel(qv, pv),
                reason="ENGINE_SEMANTICS",
            )
        )
    return diffs


def compare_cash(
    qlib: BacktestResult | None,
    prod: BacktestResult,
    *,
    tolerance: float = 1e-6,
) -> list[ConsistencyDiff]:
    """按日比较现金。"""
    q_map = {
        p.trading_date: float(p.cash)
        for p in (qlib.portfolio_history if qlib else [])
    }
    diffs: list[ConsistencyDiff] = []
    for p in prod.portfolio_history:
        qv = q_map.get(p.trading_date)
        pv = float(p.cash)
        if qv is None:
            continue
        ad = pv - qv
        if abs(ad) <= tolerance:
            continue
        diffs.append(
            ConsistencyDiff(
                dimension="cash",
                trading_date=p.trading_date,
                qlib_value=qv,
                quantdinger_value=pv,
                absolute_diff=ad,
                relative_diff=_rel(qv, pv),
                reason="ENGINE_SEMANTICS",
            )
        )
    return diffs


def compare_positions(
    qlib: BacktestResult | None,
    prod: BacktestResult,
    *,
    tolerance: float = 1e-6,
) -> list[ConsistencyDiff]:
    """按 (date, instrument) 比较持仓数量。"""
    q_map: dict[tuple[str, str], float] = {}
    if qlib:
        for p in qlib.position_history:
            q_map[(p.trading_date, p.instrument_key)] = float(p.quantity)
    diffs: list[ConsistencyDiff] = []
    seen: set[tuple[str, str]] = set()
    for p in prod.position_history:
        key = (p.trading_date, p.instrument_key)
        seen.add(key)
        qv = q_map.get(key, 0.0 if qlib else None)
        pv = float(p.quantity)
        if qv is None:
            continue
        ad = pv - qv
        if abs(ad) <= tolerance:
            continue
        diffs.append(
            ConsistencyDiff(
                dimension="position",
                instrument=p.instrument_key,
                trading_date=p.trading_date,
                qlib_value=qv,
                quantdinger_value=pv,
                absolute_diff=ad,
                relative_diff=_rel(qv, pv),
                reason="ENGINE_SEMANTICS",
            )
        )
    if qlib:
        for key, qv in q_map.items():
            if key in seen or abs(qv) <= tolerance:
                continue
            diffs.append(
                ConsistencyDiff(
                    dimension="position",
                    instrument=key[1],
                    trading_date=key[0],
                    qlib_value=qv,
                    quantdinger_value=0.0,
                    absolute_diff=-qv,
                    reason="ENGINE_SEMANTICS",
                )
            )
    return diffs


def compare_trades(
    qlib: BacktestResult | None,
    prod: BacktestResult,
) -> list[ConsistencyDiff]:
    """成交数量汇总差异（按日+标的+方向）。"""
    def _key(t):
        day = ""
        if t.execution_time is not None:
            day = t.execution_time.date().isoformat()
        elif t.order_time is not None:
            day = t.order_time.date().isoformat()
        return (day, t.instrument_key, t.side)

    def _agg(result: BacktestResult | None) -> dict[tuple, float]:
        out: dict[tuple, float] = {}
        if not result:
            return out
        for t in result.trades:
            if t.status not in ("FILLED", "PARTIAL") or t.quantity <= 0:
                continue
            k = _key(t)
            out[k] = out.get(k, 0.0) + float(t.quantity)
        return out

    q_map = _agg(qlib)
    p_map = _agg(prod)
    keys = set(q_map) | set(p_map)
    diffs: list[ConsistencyDiff] = []
    for k in sorted(keys):
        qv = q_map.get(k, 0.0)
        pv = p_map.get(k, 0.0)
        if abs(qv - pv) < 1e-9:
            continue
        diffs.append(
            ConsistencyDiff(
                dimension="trade",
                instrument=k[1],
                trading_date=k[0] or None,
                qlib_value=qv if qlib else None,
                quantdinger_value=pv,
                absolute_diff=pv - qv,
                reason="ENGINE_SEMANTICS",
            )
        )
    return diffs


def compare_costs(
    qlib: BacktestResult | None,
    prod: BacktestResult,
) -> list[ConsistencyDiff]:
    """累计佣金+税+滑点。"""
    def _sum(result: BacktestResult | None) -> float:
        if not result:
            return 0.0
        total = 0.0
        for t in result.trades:
            total += float(t.commission or 0.0)
            total += float(t.tax or 0.0)
            total += float(t.slippage or 0.0)
        return total

    qv = _sum(qlib) if qlib else None
    pv = _sum(prod)
    if qv is None:
        if pv <= 0:
            return []
        return [
            ConsistencyDiff(
                dimension="cost",
                qlib_value=None,
                quantdinger_value=pv,
                absolute_diff=None,
                reason="COMMISSION",
            )
        ]
    if abs(pv - qv) < 1e-9:
        return []
    return [
        ConsistencyDiff(
            dimension="cost",
            qlib_value=qv,
            quantdinger_value=pv,
            absolute_diff=pv - qv,
            reason="COMMISSION" if abs(pv - qv) > 0 else "OK",
        )
    ]


def collect_rejected_diffs(prod: BacktestResult) -> list[ConsistencyDiff]:
    """Production 拒单 → Diff（reason 必须 ∈ KNOWN）。"""
    diffs: list[ConsistencyDiff] = []
    for t in prod.trades:
        if t.status != "REJECTED":
            continue
        reason = t.reject_reason or "UNKNOWN"
        if reason not in KNOWN_DIFF_REASONS:
            reason = "UNKNOWN"
        day = None
        if t.order_time is not None:
            day = t.order_time.date().isoformat()
        diffs.append(
            ConsistencyDiff(
                dimension="rejected",
                instrument=t.instrument_key,
                trading_date=day,
                qlib_value=0.0,
                quantdinger_value=0.0,
                absolute_diff=0.0,
                reason=reason,
            )
        )
    return diffs


def max_abs_diff(diffs: list[ConsistencyDiff], dimension: str) -> float:
    """取某维度绝对差最大值。"""
    m = 0.0
    for d in diffs:
        if d.dimension != dimension or d.absolute_diff is None:
            continue
        m = max(m, abs(d.absolute_diff))
    return m


def annotate_position_reasons(
    diffs: list[ConsistencyDiff],
    rejected: list[ConsistencyDiff],
) -> list[ConsistencyDiff]:
    """用拒单原因标注持仓差（同日同标的优先）。"""
    by_key: dict[tuple[str | None, str | None], str] = {}
    for r in rejected:
        if r.reason and r.reason != "UNKNOWN":
            by_key[(r.trading_date, r.instrument)] = r.reason
    out: list[ConsistencyDiff] = []
    for d in diffs:
        if d.dimension == "position":
            reason = by_key.get((d.trading_date, d.instrument), d.reason)
            out.append(d.model_copy(update={"reason": reason}))
        else:
            out.append(d)
    return out
