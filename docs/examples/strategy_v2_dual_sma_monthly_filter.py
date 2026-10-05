"""双均线交叉策略 (Dual Moving Average Crossover)
Trades long-only on a dual SMA crossover using completed daily bars.
Open only when the last completed monthly MACD DIF is above 0.
"""

# @param fast_period int 10 Fast moving average period range=5:50:5
# @param slow_period int 30 Slow moving average period range=20:200:10
# @param macd_fast int 12 Monthly MACD fast EMA period range=2:100:1
# @param macd_slow int 26 Monthly MACD slow EMA period range=3:200:1
# @param target_pct float 0.95 Target portfolio weight range=0.1:1.0:0.05
# @param stop_loss_pct float 0.05 Stop loss percentage range=0.01:0.2:0.01


def macd_dif(series, fast, slow):
    """月线 DIF = 快 EMA - 慢 EMA，用来判断是否在 0 轴上方。"""
    return series.ewm(span=fast, adjust=False).mean() - series.ewm(
        span=slow, adjust=False
    ).mean()


def completed_monthly_dif_above_zero(close, fast, slow):
    """
    已收盘月线 DIF 是否在 0 轴上方，对齐到每根日线。

    月线不是策略原生周期，用日线收盘按月聚合。整体后移一根，
    使该月 DIF 从下一月才生效。时间无效时返回全 False，从而不开多。
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
    """声明恒生电子日线。预热保持 200，避免 A 股 3 年日线上限把可选区间收成 0 天。"""
    g.symbol = "CNStock:600570"
    context.set_universe([g.symbol])
    context.subscribe(
        frequency="1D",
        fields=["open", "high", "low", "close", "volume"],
    )
    context.set_warmup(200)
    context.set_benchmark("CNStock:600570")


def handle_data(context, data):
    """金叉且上一根已收盘月线 DIF > 0 才开多；死叉照常平多。"""
    fast_period = int(context.params.get("fast_period", 10))
    slow_period = int(context.params.get("slow_period", 30))
    macd_fast = int(context.params.get("macd_fast", 12))
    macd_slow = int(context.params.get("macd_slow", 26))
    target_pct = float(context.params.get("target_pct", 0.95))
    stop_loss_pct = float(context.params.get("stop_loss_pct", 0.05))

    # 均线至少要 slow+2 根；多取的日线只用于月线 DIF，不够 26 个月也继续算均线
    monthly_lookback = (macd_slow + 3) * 23
    bars = get_history(
        max(slow_period + 2, monthly_lookback),
        "1D",
        "close",
        g.symbol,
    )
    if len(bars) < slow_period + 1:
        return

    closes = bars["close"]
    fast_ma = closes.tail(fast_period).mean()
    slow_ma = closes.tail(slow_period).mean()
    prev_fast = closes.iloc[-2 - fast_period:-2].mean()
    prev_slow = closes.iloc[-2 - slow_period:-2].mean()

    position = get_position(g.symbol)
    golden_cross = fast_ma > slow_ma and prev_fast <= prev_slow
    death_cross = fast_ma < slow_ma and prev_fast >= prev_slow
    monthly_ok = bool(completed_monthly_dif_above_zero(closes, macd_fast, macd_slow).iloc[-1])

    if golden_cross and monthly_ok and position.amount <= 0:
        order_target_percent(
            g.symbol, target_pct,
            reason="dual_sma_golden_cross",
            stop_loss_pct=stop_loss_pct,
        )
    elif death_cross and position.amount > 0:
        order_target_percent(g.symbol, 0.0, reason="dual_sma_death_cross")
