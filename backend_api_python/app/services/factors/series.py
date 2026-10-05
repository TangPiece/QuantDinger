"""把因子库里的一个因子展开成与当前 K 线等长的副图序列。

图表侧按指标 ``output.plots`` 绘制。历史不够、面板对不上的位置是 None，
不让一根失败的 K 线把整条线丢掉。
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from app.services.factors.registry import FactorError, compute_factor, get_factor
from app.services.factors.talib_adapter import compute_talib_indicator
from app.services.strategy_v2.frequencies import normalize_frequency

_PLOT_COLORS = ("#22D3EE", "#60A5FA", "#F59E0B", "#A78BFA")
_HISTOGRAM_UP = "#22C55E"
_HISTOGRAM_DOWN = "#EF4444"
_LEVEL2_NOTICE = "factorLibrary.level2PanelNotice"
_LEVEL2_FETCHING = "factorLibrary.level2Fetching"
# 这些基础列围绕 0。均值和偏度仍用柱，标准差是非负波动，改回折线。
_SIGNED_LEVEL2 = frozenset({
    "l2_obi",
    "l2_ofi",
    "l2_order_ratio",
    "l2_active_net_buy",
    "l2_big_net_inflow_rate",
    "l2_auction_imbalance",
    "l2_ret_overnight",
    "l2_ret_open_30",
    "l2_ret_tail_30",
    "l2_ret_intraday",
    "l2_rskew",
})
_ROLLUP_SUFFIX = re.compile(r"_(mean|std|skew)_\d+$")


def bars_to_frame(bars: list) -> pd.DataFrame:
    """把图表传来的 K 线变成带 UTC 时间索引的行情表。空表抛 ``factor.noData``。"""
    if not isinstance(bars, list) or not bars:
        raise FactorError("factor.noData")
    stamps = []
    rows = []
    for item in bars:
        if not isinstance(item, dict):
            continue
        raw = item.get("time", item.get("timestamp"))
        try:
            stamp = float(raw)
        except (TypeError, ValueError):
            continue
        # 图表有的用秒，有的用毫秒。小于 1e10 视为秒。
        if stamp < 1e10:
            stamp *= 1000.0
        stamps.append(pd.to_datetime(stamp, unit="ms", utc=True))
        rows.append({
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "close": item.get("close"),
            "volume": item.get("volume"),
        })
    if not rows:
        raise FactorError("factor.noData")
    frame = pd.DataFrame(rows, index=pd.DatetimeIndex(stamps))
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def build_factor_plot(
    factor_id: str,
    frame: pd.DataFrame,
    *,
    market: str = "",
    symbol: str = "",
    timeframe: str = "1d",
    params: Mapping[str, Any] | None = None,
    level2_enricher: Callable | None = None,
    fundamental_enricher: Callable | None = None,
    level2_filler: Callable | None = None,
    level2_cache: Any | None = None,
) -> dict[str, Any]:
    """返回指标 ``output`` 结构：一条因子一条副图线，多输出仍放在同一副图。

    ``level2_enricher`` / ``fundamental_enricher`` 缺省时走现有面板。
    Level2 存库因子默认只展示已有数据，缺日为 null，不自动补算；
    仅当调用方显式传入 ``level2_filler`` 时才走后台补数（测试/兼容）。
    """
    key = str(factor_id or "").strip()
    if frame is None or frame.empty:
        raise FactorError("factor.noData")
    merged = dict(params or {})
    if key.lower().startswith("talib:"):
        plots = _talib_plots(key, frame, merged)
        return {"name": key, "plots": plots, "signals": [], "notice_key": None}

    definition = get_factor(key)
    notice_key = None
    working = frame
    if definition.factor_type == "level2":
        # 逐笔面板只有 A 股日线。其它周期整段留空，并带上已有说明。
        if _level2_applies(market, timeframe):
            working = _attach_level2(working, market, symbol, level2_enricher, level2_cache)
        else:
            notice_key = _LEVEL2_NOTICE
        values = _column_series(working, key) if notice_key is None else [None] * len(working)
        if notice_key is None:
            # 生产路径不再自动 schedule_symbol_fill；缺数由批量脚本手动补。
            # 显式注入 level2_filler 时保留旧补数语义（测试用）。
            if level2_filler is not None:
                started = bool(level2_filler(symbol, _trade_dates(frame)))
                if not any(item is not None for item in values):
                    notice_key = _LEVEL2_FETCHING if started else _LEVEL2_NOTICE
            elif not any(item is not None for item in values):
                notice_key = _LEVEL2_NOTICE
        return _plot_payload(key, values, notice_key, _level2_plot_type(key))

    if definition.factor_type == "fundamental":
        working = _attach_fundamental(working, market, symbol, fundamental_enricher)
    values = _prefix_series(key, working, merged)
    return _plot_payload(key, values, None, "line")


def _level2_plot_type(factor_id: str) -> str:
    """围绕 0 的列用柱状，标准差和其余幅度类列用折线。"""
    match = _ROLLUP_SUFFIX.search(factor_id)
    stat = match.group(1) if match else ""
    base = factor_id[: match.start()] if match else factor_id
    if stat == "std" or base not in _SIGNED_LEVEL2:
        return "line"
    return "histogram"


def _plot_payload(name: str, values: list, notice_key: str | None, plot_type: str) -> dict[str, Any]:
    data = [_histogram_point(item) for item in values] if plot_type == "histogram" else values
    return {
        "name": name,
        "plots": [{
            "name": name,
            "data": data,
            "overlay": False,
            "type": plot_type,
            "color": _PLOT_COLORS[0],
        }],
        "signals": [],
        "notice_key": notice_key,
    }


def _histogram_point(value: float | None) -> dict[str, float | str] | None:
    """空值保持 null。零轴及以上为绿，以下为红。"""
    if value is None:
        return None
    return {
        "value": value,
        "color": _HISTOGRAM_UP if value >= 0 else _HISTOGRAM_DOWN,
    }


def _level2_applies(market: str, timeframe: str) -> bool:
    return str(market or "").strip() == "CNStock" and normalize_frequency(timeframe) == "1d"


def _schedule_level2_fill(symbol: str, dates: list[str]) -> bool:
    from app.services.level2_factors.build import schedule_symbol_fill

    return schedule_symbol_fill(symbol, dates)


def _trade_dates(frame: pd.DataFrame) -> list[str]:
    """K 线时间换成上海交易日，供按标的补明细。"""
    from app.services.level2_factor_panel import session_dates

    stamps = session_dates(frame.index)
    return sorted({stamp.strftime("%Y%m%d") for stamp in stamps if not pd.isna(stamp)})


def _attach_level2(
    frame: pd.DataFrame,
    market: str,
    symbol: str,
    enricher: Callable | None,
    cache=None,
) -> pd.DataFrame:
    from app.services.level2_factor_panel import canonical_symbol, enrich_panel

    key = canonical_symbol(symbol)
    members = [{"key": key, "symbol": key, "market": market}]
    joiner = enricher or enrich_panel
    enriched = joiner({key: frame}, members)
    result = enriched.get(key) if isinstance(enriched, dict) else None
    working = result if isinstance(result, pd.DataFrame) else frame
    # 生产路径只读日频 Parquet。测试仍可注入一份覆盖，核对指定交易日。
    if cache is None:
        return working
    return _overlay_factor_cache(working, key, cache)


def _overlay_factor_cache(frame: pd.DataFrame, symbol: str, cache) -> pd.DataFrame:
    """把临时表里的因子贴到对得上的交易日。读库失败时保持原表。"""
    from app.services.level2_factor_panel import session_dates

    try:
        stamps = session_dates(frame.index)
        dates = [stamp.strftime("%Y%m%d") for stamp in stamps if not pd.isna(stamp)]
        found = cache.fetch(symbol, dates)
    except Exception:
        return frame
    if not found:
        return frame
    output = frame.copy()
    columns: set[str] = set()
    for factors in found.values():
        columns.update(str(key) for key in factors if str(key).startswith("l2_"))
    for column in columns:
        if column not in output.columns:
            output[column] = float("nan")
    for position, stamp in enumerate(stamps):
        if pd.isna(stamp):
            continue
        factors = found.get(stamp.strftime("%Y%m%d"))
        if not factors:
            continue
        for column in columns:
            value = factors.get(column)
            output.iat[position, output.columns.get_loc(column)] = value if isinstance(value, (int, float)) else float("nan")
    return output


def _attach_fundamental(frame: pd.DataFrame, market: str, symbol: str, enricher: Callable | None) -> pd.DataFrame:
    if enricher is not None:
        enriched = enricher(frame)
        return enriched if isinstance(enriched, pd.DataFrame) else frame
    from app.services.fundamental_data import get_fundamental_data_service

    try:
        return get_fundamental_data_service().enrich_frame(
            market=str(market or ""),
            symbol=str(symbol or ""),
            frame=frame,
        )
    except Exception:
        return frame


def _prefix_series(factor_id: str, frame: pd.DataFrame, params: Mapping[str, Any]) -> list:
    """每一根只用截至该根的历史，和回测里 ``factor()`` 看见的窗口一致。"""
    values: list = []
    for end in range(1, len(frame) + 1):
        try:
            number = compute_factor(factor_id, frame.iloc[:end], params)
        except FactorError:
            values.append(None)
            continue
        values.append(_finite_or_none(number))
    return values


def _column_series(frame: pd.DataFrame, column: str) -> list:
    if column not in frame.columns:
        return [None] * len(frame)
    numeric = pd.to_numeric(frame[column], errors="coerce")
    return [_finite_or_none(item) for item in numeric.tolist()]


def _talib_plots(factor_id: str, frame: pd.DataFrame, params: Mapping[str, Any]) -> list[dict]:
    result = compute_talib_indicator(factor_id, frame, params)
    if isinstance(result, pd.DataFrame):
        plots = []
        for index, column in enumerate(result.columns):
            plots.append({
                "name": str(column),
                "data": _column_series(result, str(column)),
                "overlay": False,
                "type": "line",
                "color": _PLOT_COLORS[index % len(_PLOT_COLORS)],
            })
        return plots
    return [{
        "name": factor_id,
        "data": [_finite_or_none(item) for item in pd.to_numeric(result, errors="coerce").tolist()],
        "overlay": False,
        "type": "line",
        "color": _PLOT_COLORS[0],
    }]


def _finite_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = ["bars_to_frame", "build_factor_plot"]
