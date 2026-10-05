"""Qlib PORT_METRIC / INDICATOR_METRIC → Domain BacktestResult 字段。"""

from __future__ import annotations

import math
import uuid
from typing import Any

import pandas as pd

from app.services.research_data.backtest.ledger import (
    EquityPoint,
    PortfolioSnapshot,
    PositionSnapshot,
    TradeRecord,
)
from app.services.research_data.backtest.result import BacktestMetrics
def _safe_float(value: Any) -> float | None:
    """将标量转为 float；NaN/Inf → None。"""
    try:
        if value is None:
            return None
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _from_qlib_instrument(qid: str) -> str:
    """sz000001 / SH600000 → CNStock:000001（尽力；失败则原样）。"""
    text = str(qid or "").strip()
    upper = text.upper()
    if len(upper) >= 8 and upper[:2] in ("SH", "SZ") and upper[2:].isdigit():
        return f"CNStock:{upper[2:]}"
    if text.isdigit() and len(text) == 6:
        return f"CNStock:{text}"
    return text


def _pick_report_frame(
    portfolio_dict: dict[str, Any] | None,
) -> tuple[pd.DataFrame | None, dict | None]:
    """从 PORT_METRIC 取日频 report + positions。"""
    if not portfolio_dict:
        return None, None
    # 优先 1day
    for key in ("1day", "day", "1d"):
        if key in portfolio_dict:
            report, positions = portfolio_dict[key]
            return report, positions
    # 任意第一个
    report, positions = next(iter(portfolio_dict.values()))
    return report, positions


def map_equity_curve(report: pd.DataFrame | None) -> list[EquityPoint]:
    """report['account'] → EquityPoint 列表，并计算 drawdown。"""
    if report is None or report.empty or "account" not in report.columns:
        return []
    equity = report["account"].astype(float)
    peak = equity.cummax()
    dd = (equity / peak) - 1.0
    points: list[EquityPoint] = []
    for ts, val in equity.items():
        trading_date = pd.Timestamp(ts).strftime("%Y-%m-%d")
        points.append(
            EquityPoint(
                trading_date=trading_date,
                timestamp=pd.Timestamp(ts).to_pydatetime(),
                equity=float(val),
                drawdown=_safe_float(dd.loc[ts]),
            )
        )
    return points


def map_metrics(report: pd.DataFrame | None) -> BacktestMetrics:
    """从权益曲线推导常用指标；有则填。"""
    if report is None or report.empty or "account" not in report.columns:
        return BacktestMetrics()
    equity = report["account"].astype(float)
    if len(equity) < 2:
        return BacktestMetrics(
            total_return=_safe_float(equity.iloc[-1] / equity.iloc[0] - 1.0)
            if equity.iloc[0]
            else None
        )
    rets = equity.pct_change().dropna()
    total_return = _safe_float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    # 年化：按 252 交易日
    mean = float(rets.mean()) if len(rets) else 0.0
    std = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    annualized = mean * 252
    vol = std * math.sqrt(252) if std else None
    sharpe = (mean / std * math.sqrt(252)) if std and std > 0 else None
    peak = equity.cummax()
    max_dd = _safe_float(((equity / peak) - 1.0).min())
    turnover = None
    if "turnover" in report.columns:
        turnover = _safe_float(report["turnover"].astype(float).mean())
    calmar = None
    if max_dd is not None and max_dd < 0 and annualized is not None:
        calmar = _safe_float(annualized / abs(max_dd))
    return BacktestMetrics(
        total_return=total_return,
        annualized_return=_safe_float(annualized),
        volatility=_safe_float(vol),
        sharpe=_safe_float(sharpe),
        max_drawdown=max_dd,
        calmar=calmar,
        turnover=turnover,
    )


def map_position_history(positions: dict | None) -> list[PositionSnapshot]:
    """Qlib hist positions → PositionSnapshot（尽力）。"""
    if not positions:
        return []
    out: list[PositionSnapshot] = []
    for ts, pos in positions.items():
        trading_date = pd.Timestamp(ts).strftime("%Y-%m-%d")
        try:
            amount_dict = pos.get_stock_amount_dict()
            weight_dict = (
                pos.get_stock_weight_dict(only_stock=True)
                if hasattr(pos, "get_stock_weight_dict")
                else {}
            )
        except Exception:
            continue
        for stock_id, amount in (amount_dict or {}).items():
            out.append(
                PositionSnapshot(
                    instrument_key=_from_qlib_instrument(stock_id),
                    trading_date=trading_date,
                    quantity=float(amount),
                    weight=_safe_float((weight_dict or {}).get(stock_id)),
                )
            )
    return out


def map_portfolio_history(
    report: pd.DataFrame | None,
    positions: dict | None,
) -> list[PortfolioSnapshot]:
    """组合日度快照。"""
    if report is None or report.empty:
        return []
    pos_by_date: dict[str, list[PositionSnapshot]] = {}
    for snap in map_position_history(positions):
        pos_by_date.setdefault(snap.trading_date, []).append(snap)

    out: list[PortfolioSnapshot] = []
    for ts, row in report.iterrows():
        trading_date = pd.Timestamp(ts).strftime("%Y-%m-%d")
        out.append(
            PortfolioSnapshot(
                trading_date=trading_date,
                cash=float(row["cash"]) if "cash" in report.columns else 0.0,
                total_value=float(row["account"]) if "account" in report.columns else 0.0,
                positions=pos_by_date.get(trading_date, []),
            )
        )
    return out


def map_trades_from_indicator(
    indicator_dict: dict[str, Any] | None,
) -> list[TradeRecord]:
    """尽力从 INDICATOR_METRIC DataFrame 提取成交；字段因版本而异。"""
    if not indicator_dict:
        return []
    frame = None
    for key in ("1day", "day", "1d"):
        if key in indicator_dict:
            frame = indicator_dict[key][0]
            break
    if frame is None:
        frame = next(iter(indicator_dict.values()))[0]
    if frame is None or (hasattr(frame, "empty") and frame.empty):
        return []

    trades: list[TradeRecord] = []
    # 常见列名兜底
    cols = {c.lower(): c for c in frame.columns}
    stock_col = cols.get("stock_id") or cols.get("instrument") or cols.get("symbol")
    amount_col = cols.get("deal_amount") or cols.get("amount") or cols.get("quantity")
    price_col = cols.get("deal_price") or cols.get("price") or cols.get("trade_price")
    dir_col = cols.get("direction") or cols.get("side") or cols.get("trade_dir")
    if not stock_col or not amount_col:
        return []

    for i, row in frame.iterrows():
        stock = str(row[stock_col])
        qty = _safe_float(row[amount_col]) or 0.0
        if abs(qty) < 1e-12:
            continue
        side = "BUY"
        if dir_col is not None:
            raw = row[dir_col]
            text = str(raw).upper()
            if "SELL" in text or text in ("-1", "0"):
                side = "SELL"
            elif isinstance(raw, (int, float)) and float(raw) < 0:
                side = "SELL"
        trades.append(
            TradeRecord(
                trade_id=f"qlib_{i}_{uuid.uuid4().hex[:8]}",
                instrument_key=_from_qlib_instrument(stock),
                side=side,
                quantity=abs(qty),
                executed_price=_safe_float(row[price_col]) if price_col else None,
                status="FILLED",
            )
        )
    return trades


def map_qlib_outputs(
    portfolio_dict: dict[str, Any] | None,
    indicator_dict: dict[str, Any] | None,
) -> dict[str, Any]:
    """统一映射入口：返回 equity/trades/positions/portfolio/metrics。"""
    report, positions = _pick_report_frame(portfolio_dict)
    return {
        "equity_curve": map_equity_curve(report),
        "metrics": map_metrics(report),
        "position_history": map_position_history(positions),
        "portfolio_history": map_portfolio_history(report, positions),
        "trades": map_trades_from_indicator(indicator_dict),
        "report": report,
    }
