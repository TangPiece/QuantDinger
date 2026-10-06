"""最小 Golden：少量股票/交易日 + PIT fundamental + 停牌占位。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import FeatureDefinition, PricePolicy
from app.services.research_data.data_query import DataQuery
from app.services.research_data.factor_lab import FactorComputeService, register_factor
from app.services.research_data.factor_lab.artifact_store import FactorDatasetArtifactStore
from app.services.research_data.registry import LocalJsonRegistry
from app.services.research_data.writer import write_market_daily, write_pit_fundamental

INSTRUMENTS = ["CNStock:600000", "CNStock:600519", "CNStock:000001"]


def trading_days(start: str = "2024-05-06", n: int = 25) -> list[date]:
    """连续工作日。"""
    cur = date.fromisoformat(start)
    out: list[date] = []
    while len(out) < n:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def seed_market(store: LocalCanonicalStore, registry: LocalJsonRegistry) -> list[date]:
    """写入 2024-05 日线。"""
    days = trading_days()
    rows = []
    for i, day in enumerate(days):
        for j, ik in enumerate(INSTRUMENTS):
            base = 10.0 + j * 5.0 + i * 0.2
            # 中间一天缺失 close 模拟缺失（volume=0）
            close = base if not (i == 8 and j == 0) else float("nan")
            rows.append(
                {
                    "instrument_key": ik,
                    "trading_date": day,
                    "open": base,
                    "high": base * 1.01,
                    "low": base * 0.99,
                    "close": close if close == close else base,  # nan check
                    "volume": 0.0 if (i == 8 and j == 0) else 1e6,
                    "amount": 1e7,
                    "vwap": base,
                    "data_version": "v1",
                }
            )
    # 分月写
    by_m: dict[int, list] = {}
    for r in rows:
        by_m.setdefault(r["trading_date"].month, []).append(r)
    for month, mrows in by_m.items():
        # 清洗 nan close
        clean = []
        for r in mrows:
            c = dict(r)
            if c["close"] != c["close"]:
                c["close"] = c["open"]
            clean.append(c)
        write_market_daily(
            store,
            pa.Table.from_pylist(clean),
            exchange="CN",
            year=2024,
            month=month,
            version="golden_4b",
            registry=registry,
        )
    return days


def seed_pit_fundamental(store: LocalCanonicalStore, registry: LocalJsonRegistry) -> None:
    """ROE：available_time=2024-05-02，用于 leakage 测试。"""
    rows = []
    for ik in INSTRUMENTS:
        rows.append(
            {
                "instrument_key": ik,
                "metric_code": "roe",
                "report_period_start": date(2024, 1, 1),
                "report_period_end": date(2024, 3, 31),
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "publish_time": datetime(2024, 5, 1, 8, 0, 0, tzinfo=timezone.utc),
                "available_time": datetime(2024, 5, 2, 0, 0, 0, tzinfo=timezone.utc),
                "value": 0.12,
                "unit": "ratio",
                "currency": "CNY",
                "revision": 1,
                "is_restatement": False,
                "source": "golden",
                "source_record_id": f"{ik}-roe-q1",
                "data_version": "pit_v1",
            }
        )
    write_pit_fundamental(
        store,
        pa.Table.from_pylist(rows),
        exchange="CN",
        year=2024,
        version="golden_pit_4b",
        registry=registry,
    )


def make_env(tmp_path: Path):
    """构造 store/registry/query/service。"""
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    query = DataQuery(store, registry)
    days = seed_market(store, registry)
    seed_pit_fundamental(store, registry)
    svc = FactorComputeService(
        query,
        registry,
        store,
        artifact_store=FactorDatasetArtifactStore(root=tmp_path / "factor_art"),
    )
    return store, registry, query, svc, days


def register_momentum(registry: LocalJsonRegistry, *, version: str = "1.0.0") -> FeatureDefinition:
    return register_factor(
        registry,
        FeatureDefinition(
            code="momentum_20d",
            version=version,
            name="Momentum 20D",
            expression="momentum_20",
            factor_type="TECHNICAL",
            computation_engine="quantdinger",
            dependencies=["market:CNStock"],
            information_policy="NON_PIT",
            price_policy=PricePolicy(adjustment="none"),
        ),
    )


def register_roe(registry: LocalJsonRegistry) -> FeatureDefinition:
    return register_factor(
        registry,
        FeatureDefinition(
            code="roe",
            version="1.0.0",
            name="ROE",
            expression="roe",
            factor_type="FUNDAMENTAL",
            computation_engine="quantdinger",
            dependencies=["fundamental:roe", "market:CNStock"],
            information_policy="PIT_SAFE",
            price_policy=PricePolicy(adjustment="none"),
        ),
    )
