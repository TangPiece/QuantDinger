"""MACD + KDJ Signal
Long-only SPY strategy converted from the chart indicator of the same name.
Enter on the rising edge of MACD hist > 0 and DIF > DEA
only when the last completed monthly DIF is above 0;
exit on the rising edge of K, D, J all above the overbought threshold.
"""

# @param macd_fast int 12 MACD fast EMA period range=2:100:1
# @param macd_slow int 26 MACD slow EMA period range=3:200:1
# @param macd_signal int 9 MACD signal EMA period range=2:100:1
# @param kdj_n int 9 KDJ lookback period range=2:100:1
# @param kdj_k_smooth int 3 K smoothing period range=1:20:1
# @param kdj_d_smooth int 3 D smoothing period range=1:20:1
# @param overbought float 80 Overbought threshold range=50:100:1
# @param target_pct float 0.95 Target portfolio weight range=0.05:1:0.05
# @param stop_loss_pct float 0.05 Stop loss on entry range=0.005:0.2:0.005

import numpy as np


def macd_dif(series, fast, slow):
    """DIF = 快 EMA - 慢 EMA，与图表指标的 MACD 快线一致。"""
    return series.ewm(span=fast, adjust=False).mean() - series.ewm(
        span=slow, adjust=False
    ).mean()


def completed_monthly_dif_above_zero(close, fast, slow):
    """
    已收盘月线 DIF 是否在 0 轴上方，对齐到每根日线。

    月线不是策略原生周期，只能用日线收盘按月聚合。整体后移一根，
    使该月 DIF 从下一月才生效，避免用尚未走完的月收盘。
    索引不是时间、或时间全部无效时返回全 False，从而不开多。
    """
    stamps = close.index
    if not isinstance(stamps, pd.DatetimeIndex):
        stamps = pd.to_datetime(stamps, errors="coerce")
        stamps = pd.DatetimeIndex(stamps)
    # .all() 会在沙箱里导入被禁的 numpy._core._methods
    if len(stamps) == 0 or int(stamps.isna().sum()) == len(stamps):
        return pd.Series(False, index=close.index)

    monthly_close = (
        pd.Series(close.to_numpy(), index=stamps)
        .sort_index()
        .resample("MS")
        .last()
        .dropna()
    )
    if monthly_close.empty:
        return pd.Series(False, index=close.index)
    closed_dif = macd_dif(monthly_close, fast, slow).shift(1)
    aligned = closed_dif.reindex(stamps, method="ffill")
    return pd.Series((aligned > 0).fillna(False).to_numpy(), index=close.index)


def initialize(context):
    """声明标的、日线订阅与纯多方向；warmup 只预留日线缓冲，不占满行情窗口。"""
    g.symbol = "USStock:SPY"
    context.set_universe([g.symbol])
    context.subscribe(
        frequency="1d",
        fields=["open", "high", "low", "close", "volume"],
    )
    context.set_benchmark("USStock:SPY")
    context.set_metadata(direction_mode="long_only")
    # 620 根日线会按 bars*7/5*1.35 折成约 1172 个日历日，非美股日线上限只有 1095 天，
    # 可选区间会被减成 0。180 根约 341 天，3 年上限下仍能选满 2 年。
    context.set_warmup(180)


def handle_data(context, data):
    """
    每根已收盘日线复算原指标代数，用上升沿开多/平多。
    开多还要求上一根已收盘月线 DIF > 0。手算 KDJ，避免内置 STOCH 偏差。
    """
    macd_fast = int(context.params.get("macd_fast", 12))
    macd_slow = int(context.params.get("macd_slow", 26))
    macd_signal = int(context.params.get("macd_signal", 9))
    kdj_n = int(context.params.get("kdj_n", 9))
    kdj_k_smooth = int(context.params.get("kdj_k_smooth", 3))
    kdj_d_smooth = int(context.params.get("kdj_d_smooth", 3))
    overbought = float(context.params.get("overbought", 80))
    target_pct = float(context.params.get("target_pct", 0.95))
    stop_loss_pct = float(context.params.get("stop_loss_pct", 0.05))

    # 日线信号窗口，以及约 (slow + 3) 个交易月的月线 DIF 窗口
    daily_lookback = max(macd_slow + macd_signal, kdj_n) + max(kdj_k_smooth, kdj_d_smooth) + 10
    monthly_lookback = (macd_slow + 3) * 23
    # 能取到更多日线就用来稳定月线 DIF；不够 26 个月也照常计算，不因此整段不交易
    bars = get_history(
        max(daily_lookback, monthly_lookback),
        "1d",
        ["high", "low", "close"],
        g.symbol,
    )
    if len(bars) < daily_lookback:
        return

    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)

    # --- MACD：与指标相同的 DIF / DEA / hist(*2) ---
    dif = macd_dif(close, macd_fast, macd_slow)
    dea = dif.ewm(span=macd_signal, adjust=False).mean()
    macd_hist = (dif - dea) * 2.0
    monthly_dif_above_zero = completed_monthly_dif_above_zero(close, macd_fast, macd_slow)

    # --- KDJ：RSV + ewm(alpha=1/smooth) + J=3K-2D（非 TA-Lib STOCH）---
    lowest_low = low.rolling(window=kdj_n, min_periods=kdj_n).min()
    highest_high = high.rolling(window=kdj_n, min_periods=kdj_n).max()
    range_hl = (highest_high - lowest_low).replace(0, np.nan)
    rsv = ((close - lowest_low) / range_hl * 100.0).fillna(50.0)

    alpha_k = 1.0 / max(kdj_k_smooth, 1)
    alpha_d = 1.0 / max(kdj_d_smooth, 1)
    k = rsv.ewm(alpha=alpha_k, adjust=False).mean()
    d = k.ewm(alpha=alpha_d, adjust=False).mean()
    j = 3.0 * k - 2.0 * d

    # 状态条件 → 上升沿（等价于指标里的 ~condition.shift(1)）
    buy_condition = ((macd_hist > 0) & (dif > dea) & monthly_dif_above_zero).eq(True)
    sell_condition = ((k > overbought) & (d > overbought) & (j > overbought)).eq(True)

    buy_now = bool(buy_condition.iloc[-1])
    buy_prev = bool(buy_condition.iloc[-2])
    sell_now = bool(sell_condition.iloc[-1])
    sell_prev = bool(sell_condition.iloc[-2])
    buy_event = buy_now and not buy_prev
    sell_event = sell_now and not sell_prev

    position = get_position(g.symbol)
    is_long = float(position.amount or 0.0) > 0

    # 开多 / 平多互斥；sell 仅平多，不开空
    if buy_event and not is_long:
        order_target_percent(
            g.symbol,
            target_pct,
            reason="macd_kdj_signal_entry",
            stop_loss_pct=stop_loss_pct,
        )
    elif sell_event and is_long:
        order_target_percent(
            g.symbol,
            0.0,
            reason="macd_kdj_signal_exit",
        )
