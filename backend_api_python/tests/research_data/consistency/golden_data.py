"""Phase 3E Golden Dataset 构造：5 标的 × ~20 交易日 + 分层信号。

人工场景覆盖：正常买卖、涨停、跌停、停牌、非整手、现金压力、T+1、佣金、滑点。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

import pandas as pd

from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.contracts import TargetPosition

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
INSTRUMENTS = [
    "CNStock:600000",
    "CNStock:600519",
    "CNStock:000001",
    "CNStock:000002",
    "CNStock:601318",
]
PRIMARY = "CNStock:600519"


def trading_days(start: str = "2024-05-06", end: str = "2024-05-31") -> list[str]:
    """工作日日历（周一至周五）。"""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out: list[str] = []
    cur = s
    while cur <= e:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def build_bars_by_date(
    days: list[str] | None = None,
) -> dict[str, dict[str, MarketBar]]:
    """构造 OHLCV + 状态：含涨停/跌停/停牌日。"""
    days = days or trading_days()
    bars: dict[str, dict[str, MarketBar]] = {}
    for i, day in enumerate(days):
        day_bars: dict[str, MarketBar] = {}
        for j, ik in enumerate(INSTRUMENTS):
            # 基础价：标的偏移 + 缓慢上涨
            base = 10.0 + j * 5.0 + i * 0.1
            is_limit_up = False
            is_limit_down = False
            is_suspended = False
            # L5 为 T+1：信号日 i 的 intent 在 i+1 执行，故状态打在执行日
            # Day10 信号加仓 → Day11 涨停拒买
            if ik == PRIMARY and i == 11:
                is_limit_up = True
                base = base * 1.1
            # Day12 信号清仓 → Day13 跌停拒卖
            if ik == PRIMARY and i == 13:
                is_limit_down = True
                base = base * 0.9
            # Day14 信号清仓 → Day15 停牌拒卖
            if ik == PRIMARY and i == 15:
                is_suspended = True
            day_bars[ik] = MarketBar(
                instrument_key=ik,
                trading_date=day,
                open=round(base, 2),
                high=round(base * 1.01, 2),
                low=round(base * 0.99, 2),
                close=round(base, 2),
                volume=1_000_000.0,
                is_suspended=is_suspended,
                is_limit_up=is_limit_up,
                is_limit_down=is_limit_down,
                upper_limit=round(base, 2) if is_limit_up else None,
                lower_limit=round(base, 2) if is_limit_down else None,
            )
        bars[day] = day_bars
    return bars


def build_targets_by_date(
    days: list[str] | None = None,
) -> dict[str, list[TargetPosition]]:
    """分层信号：买入 / 加仓非整手 / 清仓尝试（遇限制日）/ 再买入。"""
    days = days or trading_days()
    ds = "ds_hash_3e_golden"
    ts = datetime(2024, 5, 6, 15, 0, 0, tzinfo=timezone.utc)

    def tp(day: str, ik: str, qty: float) -> TargetPosition:
        return TargetPosition(
            instrument_key=ik,
            trading_date=day,
            portfolio_id="golden_p1",
            strategy_version="golden@1",
            dataset_hash=ds,
            timestamp=ts,
            target_quantity=qty,
            target_weight=0.0,
            signal_id=f"sig_{day}_{ik}",
        )

    targets: dict[str, list[TargetPosition]] = {}
    # Day0：买 PRIMARY 100
    targets[days[0]] = [tp(days[0], PRIMARY, 100)]
    # Day2：加仓到 155（L4 会 floor 到 100 增量→整手）
    if len(days) > 2:
        targets[days[2]] = [tp(days[2], PRIMARY, 155)]
    # Day5：买入第二标的
    if len(days) > 5:
        targets[days[5]] = [
            tp(days[5], PRIMARY, 155),
            tp(days[5], INSTRUMENTS[0], 200),
        ]
    # Day10：涨停日仍尝试加仓（L5 拒）
    if len(days) > 10:
        targets[days[10]] = [tp(days[10], PRIMARY, 300)]
    # Day12：跌停日尝试清仓（L5 拒）
    if len(days) > 12:
        targets[days[12]] = [tp(days[12], PRIMARY, 0)]
    # Day14：停牌日尝试清仓（L5 拒）
    if len(days) > 14:
        targets[days[14]] = [tp(days[14], PRIMARY, 0)]
    # Day16：正常清仓 PRIMARY
    if len(days) > 16:
        targets[days[16]] = [tp(days[16], PRIMARY, 0)]
    return targets


def write_golden_files(
    root: Path | None = None,
    bars: Mapping[str, Mapping[str, MarketBar]] | None = None,
    targets: dict[str, list[TargetPosition]] | None = None,
) -> Path:
    """写出 market.csv / signals.csv / expected 占位目录。"""
    root = root or GOLDEN_DIR
    market_dir = root / "market"
    signal_dir = root / "signals"
    expected_dir = root / "expected"
    market_dir.mkdir(parents=True, exist_ok=True)
    signal_dir.mkdir(parents=True, exist_ok=True)
    expected_dir.mkdir(parents=True, exist_ok=True)

    bars = bars or build_bars_by_date()
    targets = targets or build_targets_by_date()

    mrows = []
    for day, day_bars in bars.items():
        for ik, bar in day_bars.items():
            mrows.append(
                {
                    "trading_date": day,
                    "instrument_key": ik,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "is_suspended": bar.is_suspended,
                    "is_limit_up": bar.is_limit_up,
                    "is_limit_down": bar.is_limit_down,
                }
            )
    pd.DataFrame(mrows).to_csv(market_dir / "bars.csv", index=False)

    srows = []
    for day, items in targets.items():
        for t in items:
            srows.append(
                {
                    "trading_date": day,
                    "instrument_key": t.instrument_key,
                    "target_quantity": t.target_quantity,
                    "target_weight": t.target_weight,
                    "dataset_hash": t.dataset_hash,
                    "strategy_version": t.strategy_version,
                    "signal_id": t.signal_id,
                }
            )
    pd.DataFrame(srows).to_csv(signal_dir / "targets.csv", index=False)
    return root


def write_expected_level(
    level: str,
    equity: list[dict],
    trades: list[dict],
    positions: list[dict],
    root: Path | None = None,
) -> None:
    """写入 expected/{level}/*.parquet。"""
    root = (root or GOLDEN_DIR) / "expected" / level
    root.mkdir(parents=True, exist_ok=True)
    if equity:
        pd.DataFrame(equity).to_parquet(root / "equity.parquet", index=False)
    if trades:
        pd.DataFrame(trades).to_parquet(root / "trades.parquet", index=False)
    if positions:
        pd.DataFrame(positions).to_parquet(root / "positions.parquet", index=False)
