"""Phase 5B Golden：注入 TargetPosition + 价格面板跑研究回测。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.registry import LocalJsonRegistry
from app.services.research_data.research_backtest import (
    BacktestSpec,
    ResearchBacktestService,
    ResearchExecutionPolicy,
)

SHASH = "strat_hash_5b_golden_001"
INST_A = "CN:AAA"
INST_B = "CN:BBB"
INST_BENCH = "INDEX:000300.SH"


def make_env(tmp: Path):
    """本地 store + registry + service。"""
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    svc = ResearchBacktestService(store, registry)
    return store, registry, svc


def trading_days(n: int = 5, start: date | None = None) -> list[date]:
    d0 = start or date(2020, 1, 2)
    # 简单连续日历（测试不关心周末）
    return [d0 + timedelta(days=i) for i in range(n)]


def price_bars(
    days: list[date] | None = None,
    *,
    a_open: list[float] | None = None,
    a_close: list[float] | None = None,
    b_open: list[float] | None = None,
    b_close: list[float] | None = None,
    include_bench: bool = False,
) -> list[dict[str, Any]]:
    """构造可手算的日线。"""
    days = days or trading_days(5)
    # 默认：A 每日 open=close=10,11,12,...；B 恒 20
    if a_close is None:
        a_close = [10.0 + i for i in range(len(days))]
    if a_open is None:
        a_open = list(a_close)  # 开盘=昨收简化；首日同 close
        for i in range(1, len(a_open)):
            a_open[i] = a_close[i - 1]
    if b_close is None:
        b_close = [20.0] * len(days)
    if b_open is None:
        b_open = list(b_close)

    rows: list[dict[str, Any]] = []
    for i, d in enumerate(days):
        rows.append(
            {
                "instrument_key": INST_A,
                "trading_date": d.isoformat(),
                "open": a_open[i],
                "close": a_close[i],
                "high": a_close[i],
                "low": a_open[i],
            }
        )
        rows.append(
            {
                "instrument_key": INST_B,
                "trading_date": d.isoformat(),
                "open": b_open[i],
                "close": b_close[i],
                "high": b_close[i],
                "low": b_open[i],
            }
        )
        if include_bench:
            # 基准日收益约 1%
            rows.append(
                {
                    "instrument_key": INST_BENCH,
                    "trading_date": d.isoformat(),
                    "open": 1000.0 * (1.01**i),
                    "close": 1000.0 * (1.01 ** (i + 1)),
                    "high": 1000.0 * (1.01 ** (i + 1)),
                    "low": 1000.0 * (1.01**i),
                }
            )
    return rows


def long_only_targets(days: list[date]) -> dict[str, list[dict[str, Any]]]:
    """每日信号：100% A（信号日 = 日历日）。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for d in days:
        out[d.isoformat()] = [
            {"instrument_key": INST_A, "target_weight": 1.0},
        ]
    return out


def long_short_targets(days: list[date]) -> dict[str, list[dict[str, Any]]]:
    """每日：+1 A / -1 B。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for d in days:
        out[d.isoformat()] = [
            {"instrument_key": INST_A, "target_weight": 1.0},
            {"instrument_key": INST_B, "target_weight": -1.0},
        ]
    return out


def default_spec(
    *,
    mode: str = "NEXT_OPEN",
    start: date | None = None,
    end: date | None = None,
    days: list[date] | None = None,
    benchmark_mode: str = "NONE",
) -> BacktestSpec:
    days = days or trading_days(5)
    return BacktestSpec(
        strategy_hash=SHASH,
        start_date=start or days[0],
        end_date=end or days[-1],
        execution_policy=ResearchExecutionPolicy(mode=mode),  # type: ignore[arg-type]
        benchmark_mode=benchmark_mode,  # type: ignore[arg-type]
        benchmark_instrument_key=INST_BENCH if benchmark_mode == "INDEX" else "",
        initial_nav=1.0,
    )


def run_backtest(
    svc: ResearchBacktestService,
    *,
    spec: BacktestSpec | None = None,
    targets: dict[str, list[dict[str, Any]]] | None = None,
    bars: list[dict[str, Any]] | None = None,
    force: bool = True,
    extra_meta: dict[str, Any] | None = None,
):
    days = trading_days(5)
    spec = spec or default_spec(days=days)
    meta = {
        "targets_by_date": targets or long_only_targets(days[:-1]),
        "price_bars": bars or price_bars(days),
        "force_recompute": force,
    }
    if extra_meta:
        meta.update(extra_meta)
    return svc.run(SHASH, spec, metadata=meta)
