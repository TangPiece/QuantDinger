# QuantDinger chart-only indicator example.
# Paste into Indicator IDE. This file does not backtest or trade.

# @param macd_fast int 12 MACD fast EMA period
# @param macd_slow int 26 MACD slow EMA period
# @param macd_signal int 9 MACD signal EMA period
# @param kdj_n int 9 KDJ lookback period
# @param kdj_k_smooth int 3 K smoothing period
# @param kdj_d_smooth int 3 D smoothing period
# @param overbought float 80 Overbought threshold

my_indicator_name = "MACD + KDJ Signal"
my_indicator_description = "Buy when MACD histogram > 0, DIF > DEA, and the last completed monthly DIF is above 0. Exit when K, D, J are all above 80."

df = df.copy()

macd_fast = int(params.get('macd_fast', 12))
macd_slow = int(params.get('macd_slow', 26))
macd_signal = int(params.get('macd_signal', 9))
kdj_n = int(params.get('kdj_n', 9))
kdj_k_smooth = int(params.get('kdj_k_smooth', 3))
kdj_d_smooth = int(params.get('kdj_d_smooth', 3))
overbought = float(params.get('overbought', 80))

close = df['close'].astype(float)
high = df['high'].astype(float)
low = df['low'].astype(float)


def macd_dif(series, fast, slow):
    """DIF = 快 EMA - 慢 EMA，与图表上的 MACD 快线一致。"""
    return series.ewm(span=fast, adjust=False).mean() - series.ewm(span=slow, adjust=False).mean()


def chart_timestamps(frame):
    """从索引或 time/datetime/date/timestamp 列解析 K 线时间；无法解析时返回 None。"""
    if isinstance(frame.index, pd.DatetimeIndex):
        stamps = pd.to_datetime(frame.index, errors='coerce')
    else:
        column = next(
            (name for name in ('time', 'datetime', 'date', 'timestamp') if name in frame.columns),
            None,
        )
        if column is None:
            return None
        raw = frame[column]
        # 沙箱禁止 pd.api；能整体转成数字则按 unix 时间戳处理
        numeric = pd.to_numeric(raw, errors='coerce')
        if len(raw) > 0 and numeric.notna().any() and int(numeric.notna().sum()) == int(raw.notna().sum()):
            # 大于 1e10 视为毫秒，否则视为秒
            unit = 'ms' if float(numeric.max()) > 10_000_000_000 else 's'
            stamps = pd.to_datetime(numeric, unit=unit, errors='coerce')
        else:
            stamps = pd.to_datetime(raw, errors='coerce')
    stamps = pd.DatetimeIndex(stamps)
    # .all() 会在沙箱里导入被禁的 numpy._core._methods，改用 sum 判断是否全部无效
    if int(stamps.isna().sum()) == len(stamps):
        return None
    return stamps


def completed_monthly_dif_above_zero(close_series, stamps, fast, slow):
    """
    已收盘月线 DIF 是否在 0 轴上方。

    按月初标记每月最后一根收盘，再整体后移一根，使该月 DIF 从下一月才生效，
    避免用当月尚未走完的收盘回看历史。当前图已是一月一根时，直接用本图 DIF。
    """
    if stamps.nunique() == 0:
        return pd.Series(False, index=close_series.index)
    periods = stamps.to_period('M')
    chart_dif = macd_dif(close_series, fast, slow)
    # 每根 K 线各属不同月份：本图就是月 K（或更粗），过滤等价于本图 DIF > 0
    if periods.nunique() == len(stamps):
        return (chart_dif > 0).fillna(False)

    monthly_close = (
        pd.Series(close_series.to_numpy(), index=stamps)
        .sort_index()
        .resample('MS')
        .last()
        .dropna()
    )
    if monthly_close.empty:
        return pd.Series(False, index=close_series.index)
    # 后移一根：标签为下一月月初，表示上一月已收盘
    closed_dif = macd_dif(monthly_close, fast, slow).shift(1)
    aligned = closed_dif.reindex(stamps, method='ffill')
    return pd.Series((aligned > 0).fillna(False).to_numpy(), index=close_series.index)


dif = macd_dif(close, macd_fast, macd_slow)
dea = dif.ewm(span=macd_signal, adjust=False).mean()
macd_hist = (dif - dea) * 2.0

lowest_low = low.rolling(window=kdj_n, min_periods=kdj_n).min()
highest_high = high.rolling(window=kdj_n, min_periods=kdj_n).max()
range_hl = (highest_high - lowest_low).replace(0, np.nan)
rsv = ((close - lowest_low) / range_hl * 100.0).fillna(50.0)

alpha_k = 1.0 / max(kdj_k_smooth, 1)
alpha_d = 1.0 / max(kdj_d_smooth, 1)
k = rsv.ewm(alpha=alpha_k, adjust=False).mean()
d = k.ewm(alpha=alpha_d, adjust=False).mean()
j = 3.0 * k - 2.0 * d

timestamps = chart_timestamps(df)
if timestamps is None:
    monthly_dif_above_zero = pd.Series(False, index=df.index)
else:
    monthly_dif_above_zero = completed_monthly_dif_above_zero(
        close, timestamps, macd_fast, macd_slow
    )

buy_condition = ((macd_hist > 0) & (dif > dea) & monthly_dif_above_zero).eq(True)
sell_condition = ((k > overbought) & (d > overbought) & (j > overbought)).eq(True)

# NaN 视为未满足；用 fill_value 避免 shift 后 fillna 把布尔列降成 object
buy_signal = buy_condition & ~buy_condition.shift(1, fill_value=False)
sell_signal = sell_condition & ~sell_condition.shift(1, fill_value=False)

buy_marks = [low.iloc[i] * 0.995 if bool(buy_signal.iloc[i]) else None for i in range(len(df))]
sell_marks = [high.iloc[i] * 1.005 if bool(sell_signal.iloc[i]) else None for i in range(len(df))]

output = {
    'name': my_indicator_name,
    'plots': [],
    'signals': [
        {'type': 'buy', 'text': '做多买入', 'data': buy_marks, 'color': '#52c41a'},
        {'type': 'sell', 'text': '做多卖出', 'data': sell_marks, 'color': '#ff4d4f'},
    ],
    'layers': [],
}
