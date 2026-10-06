"""最小日频因子 DSL（pandas 实现；有 polars 时可选加速）。

支持表达式关键字（大小写不敏感前缀）：
- momentum_N / pct_change_N
- rolling_mean_N(close) / rolling_std_N(close)
- volatility_N
- close/open 等 ratio：``close/open``
- Ref(close, N) 风格（无 $）
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


class DSLError(ValueError):
    """DSL 解析/执行失败。"""


_MOM = re.compile(r"^(?:momentum|pct_change)_(\d+)$", re.I)
_ROLL = re.compile(r"^rolling_(mean|std)_(\d+)\((\w+)\)$", re.I)
_VOL = re.compile(r"^volatility_(\d+)$", re.I)
_REF = re.compile(r"^Ref\(\s*(\w+)\s*,\s*(\d+)\s*\)$", re.I)
_RATIO = re.compile(r"^(\w+)\s*/\s*(\w+)$", re.I)


def evaluate_on_market(df: pd.DataFrame, expression: str) -> pd.Series:
    """在含 instrument_key/trading_date/OHLCV 的面板上求值，返回与 df 对齐的 Series。"""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    work = df.copy()
    work["trading_date"] = pd.to_datetime(work["trading_date"]).dt.normalize()
    work = work.sort_values(["instrument_key", "trading_date"]).reset_index(drop=True)
    expr = str(expression or "").strip()
    if not expr:
        raise DSLError("empty expression")

    parts: list[pd.Series] = []
    for _, g in work.groupby("instrument_key", sort=False):
        s = _eval_group(g, expr)
        s.index = g.index
        parts.append(s)
    out = pd.concat(parts).sort_index()
    return out.astype(float)


def _col(g: pd.DataFrame, name: str) -> pd.Series:
    key = name.lower()
    for c in g.columns:
        if str(c).lower() == key:
            return g[c].astype(float)
    raise DSLError(f"column not found: {name}")


def _eval_group(g: pd.DataFrame, expr: str) -> pd.Series:
    m = _MOM.match(expr)
    if m:
        n = int(m.group(1))
        close = _col(g, "close")
        return close / close.shift(n) - 1.0

    m = _VOL.match(expr)
    if m:
        n = int(m.group(1))
        close = _col(g, "close")
        ret = close.pct_change()
        return ret.rolling(n, min_periods=max(2, n // 2)).std()

    m = _ROLL.match(expr)
    if m:
        op, n_s, field = m.group(1).lower(), int(m.group(2)), m.group(3)
        s = _col(g, field)
        if op == "mean":
            return s.rolling(n_s, min_periods=1).mean()
        return s.rolling(n_s, min_periods=1).std()

    m = _REF.match(expr)
    if m:
        field, n = m.group(1), int(m.group(2))
        return _col(g, field).shift(n)

    m = _RATIO.match(expr)
    if m:
        a, b = m.group(1), m.group(2)
        den = _col(g, b)
        return _col(g, a) / den.replace(0, pd.NA)

    # 原子列
    if re.fullmatch(r"\w+", expr):
        return _col(g, expr)

    raise DSLError(f"unsupported expression: {expr!r}")


def frame_to_long_records(
    df: pd.DataFrame,
    values: pd.Series,
    *,
    factor_code: str,
    factor_version: str,
) -> list[dict[str, Any]]:
    """拼 long records。"""
    out: list[dict[str, Any]] = []
    for idx, val in values.items():
        if pd.isna(val):
            continue
        row = df.loc[idx]
        td = row["trading_date"]
        day = td.date().isoformat() if hasattr(td, "date") else str(td)[:10]
        out.append(
            {
                "instrument_key": str(row["instrument_key"]),
                "trading_date": day,
                "factor_code": factor_code,
                "factor_version": factor_version,
                "value": float(val),
            }
        )
    return out
