"""Phase 1D：PIT-safe 研究面板（Phase 2 Adapter 输入契约预演，非 Handler）。

市场 OHLCV 经 DataQuery.market；基本面必须经 DataQuery.fundamental(knowledge_time)，
禁止直接读 Canonical PIT parquet 绕过 available_time 门禁。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Sequence

import pandas as pd

from app.services.research_data.contracts import PricePolicy
from app.services.research_data.data_query import DataQuery


def build_pit_safe_research_panel(
    query: DataQuery,
    instruments: Sequence[str],
    metrics: Sequence[str],
    knowledge_time: datetime,
    *,
    market_start: date | None = None,
    market_end: date | None = None,
    price_policy: PricePolicy | None = None,
    exchange: str = "CN",
) -> pd.DataFrame:
    """构建 PIT-safe 研究面板：market OHLCV ∪ fundamental(knowledge_time)。

    Returns:
        宽表 DataFrame：每行一只票的行情摘要 + 各 metric 列（无可见值则为 NaN）。
        保证 fundamental 侧已应用 available_time <= knowledge_time。
    """
    keys = list(instruments)
    start = market_start or date(1970, 1, 1)
    end = market_end or date(2100, 1, 1)
    market = query.market(
        keys,
        start,
        end,
        price_policy=price_policy or PricePolicy(),
        exchange=exchange,
    )
    fund = query.fundamental(
        keys,
        list(metrics),
        knowledge_time,
        exchange=exchange,
    )

    # 行情侧：按 instrument 取区间内最后一行作为研究快照锚点
    if market.empty:
        base = pd.DataFrame({"instrument_key": keys})
    else:
        market = market.sort_values(["instrument_key", "trading_date"])
        base = market.groupby("instrument_key", as_index=False).tail(1).reset_index(drop=True)

    if fund.empty:
        for m in metrics:
            base[m] = float("nan")
        base["knowledge_time"] = knowledge_time
        return base

    # 透视 metric → 列；已是 PIT 过滤后的最新 revision
    wide = fund.pivot_table(
        index="instrument_key",
        columns="metric_code",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide.columns = [str(c) for c in wide.columns]
    for m in metrics:
        if m not in wide.columns:
            wide[m] = float("nan")

    out = base.merge(wide[["instrument_key", *metrics]], on="instrument_key", how="left")
    out["knowledge_time"] = knowledge_time
    # 附带 available_time 便于测试断言（取该 KT 下可见的最晚 available_time）
    avail = (
        fund.groupby("instrument_key")["available_time"]
        .max()
        .rename("fundamental_available_time")
        .reset_index()
    )
    out = out.merge(avail, on="instrument_key", how="left")
    return out
