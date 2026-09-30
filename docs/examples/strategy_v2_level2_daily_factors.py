"""Level2 日频因子周频选股
按过去 20 日主动净买入率均值排序，等权持有排名靠前的 A 股。
因子由离线面板在回测前并入日线，策略里不能读取 Parquet。
"""

# @param holdings int 10 Number of holdings range=3:30:1
# @param max_weight float 0.10 Maximum weight per holding range=0.02:0.2:0.01


def initialize(context):
    """沪深 300 日线，周频调仓。20 日均值已经在因子列里算好。"""
    context.set_universe(pool="csi300")
    context.subscribe(frequency="1d")
    context.set_warmup(20)
    context.set_benchmark("CNStock:000300.SH")
    run_weekly(rebalance, weekday=1, time="09:35")


def rebalance(context, data):
    """主动净买入率 20 日均值从高到低取前 N 只，其余降到零权重。"""
    holdings = int(context.params.get("holdings", 10))
    max_weight = float(context.params.get("max_weight", 0.10))
    symbols = get_universe_stocks()
    if len(symbols) < holdings:
        return

    scores = get_factors(symbols, ["l2_active_net_buy_mean_20", "l2_rv_mean_20"])
    column = "l2_active_net_buy_mean_20"
    if scores.empty or column not in scores.columns:
        return

    ranked = scores[column].dropna().sort_values(ascending=False)
    selected = list(ranked.head(holdings).index)
    if not selected:
        return

    target_weight = min(max_weight, 0.95 / len(selected))
    current = get_positions()
    for symbol in current:
        if symbol not in selected:
            order_target_percent(symbol, 0.0, reason="level2_remove")
    for symbol in selected:
        order_target_percent(symbol, target_weight, reason="level2_select")
