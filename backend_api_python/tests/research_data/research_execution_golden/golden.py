"""Phase 5C Golden：GROSS vs NET 成本/约束/归因。"""

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

SHASH = "strat_hash_5c_golden_001"
INST_A = "CN:AAA"
INST_B = "CN:BBB"
# CN_A 最低佣金 5 元，用足额本金避免费用主导
NAV0 = 1_000_000.0


def make_env(tmp: Path):
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    svc = ResearchBacktestService(store, registry)
    return store, registry, svc


def trading_days(n: int = 5, start: date | None = None) -> list[date]:
    d0 = start or date(2020, 1, 2)
    return [d0 + timedelta(days=i) for i in range(n)]


def price_bars(
    days: list[date] | None = None,
    *,
    a_open: list[float] | None = None,
    a_close: list[float] | None = None,
) -> list[dict[str, Any]]:
    days = days or trading_days(5)
    if a_close is None:
        # 温和上涨，便于手数整除
        a_close = [10.0 + 0.1 * i for i in range(len(days))]
    if a_open is None:
        a_open = [a_close[0]] + list(a_close[:-1])
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
                "open": 20.0,
                "close": 20.0,
                "high": 20.0,
                "low": 20.0,
            }
        )
    return rows


def long_only_targets(days: list[date]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for d in days:
        out[d.isoformat()] = [
            {"instrument_key": INST_A, "target_weight": 1.0},
        ]
    return out


def make_spec(
    *,
    realism: str = "GROSS",
    mode: str = "SAME_CLOSE",
    days: list[date] | None = None,
    market_rule: str = "CN_A",
    initial_nav: float = NAV0,
    cost_override: dict[str, Any] | None = None,
    rule_override: dict[str, Any] | None = None,
) -> BacktestSpec:
    days = days or trading_days(5)
    meta: dict[str, Any] = {}
    if cost_override is not None:
        meta["cost_policy_override"] = cost_override
    if rule_override is not None:
        meta["trading_rule_override"] = rule_override
    return BacktestSpec(
        strategy_hash=SHASH,
        start_date=days[0],
        end_date=days[-1],
        execution_policy=ResearchExecutionPolicy(mode=mode),  # type: ignore[arg-type]
        realism=realism,  # type: ignore[arg-type]
        market_rule=market_rule,  # type: ignore[arg-type]
        initial_nav=initial_nav,
        metadata=meta,
    )


def run_bt(
    svc: ResearchBacktestService,
    *,
    realism: str = "GROSS",
    cost_override: dict[str, Any] | None = None,
    rule_override: dict[str, Any] | None = None,
    days: list[date] | None = None,
    targets: dict[str, list[dict[str, Any]]] | None = None,
    bars: list[dict[str, Any]] | None = None,
    trading_status: dict | None = None,
    mode: str = "SAME_CLOSE",
):
    days = days or trading_days(5)
    spec = make_spec(
        realism=realism,
        mode=mode,
        days=days,
        cost_override=cost_override,
        rule_override=rule_override,
    )
    meta: dict[str, Any] = {
        "targets_by_date": targets or long_only_targets(days[:3]),
        "price_bars": bars or price_bars(days),
        "force_recompute": True,
    }
    if cost_override is not None:
        meta["cost_policy_override"] = cost_override
    if rule_override is not None:
        meta["trading_rule_override"] = rule_override
    if trading_status is not None:
        meta["trading_status_by_date"] = trading_status
    return svc.run(SHASH, spec, metadata=meta)
