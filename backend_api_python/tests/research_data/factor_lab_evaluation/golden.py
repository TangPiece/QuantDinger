"""最小 Golden Evaluation：手工价格 + Universe Snapshot + 停牌。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import (
    FactorDatasetRecord,
    PricePolicy,
)
from app.services.research_data.data_query import DataQuery
from app.services.research_data.factor_lab.evaluation import (
    EvaluationSpec,
    FactorEvaluationService,
    ReturnSpec,
)
from app.services.research_data.factor_lab.evaluation.artifact_store import (
    EvaluationArtifactStore,
)
from app.services.research_data.registry import LocalJsonRegistry
from app.services.research_data.writer import (
    write_market_daily,
    write_trading_status,
    write_universe_snapshot,
)

INSTRUMENTS = ["CNStock:AAA", "CNStock:BBB", "CNStock:CCC"]
UNIVERSE = "CSI300"
SNAP_A = "snap_univ_2020"
SNAP_B = "snap_univ_2026"
FACTOR_DS_ID = "fds_golden_4c_momentum"


def trading_days(start: str = "2024-05-06", n: int = 15) -> list[date]:
    """连续工作日。"""
    cur = date.fromisoformat(start)
    out: list[date] = []
    while len(out) < n:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def seed_market_handcrafted(
    store: LocalCanonicalStore, registry: LocalJsonRegistry
) -> list[date]:
    """AAA 价格序列便于手工验算：100,102,105,103,108,..."""
    days = trading_days()
    # AAA 前 6 日固定，便于 1D/5D
    aaa_closes = [100.0, 102.0, 105.0, 103.0, 108.0, 110.0]
    aaa_opens = [99.0, 100.5, 102.5, 104.0, 103.5, 108.5]
    rows = []
    for i, day in enumerate(days):
        for j, ik in enumerate(INSTRUMENTS):
            if ik == "CNStock:AAA" and i < len(aaa_closes):
                o, c = aaa_opens[i], aaa_closes[i]
            else:
                base = 50.0 + j * 10 + i
                o, c = base, base + 1.0
            rows.append(
                {
                    "instrument_key": ik,
                    "trading_date": day,
                    "open": o,
                    "high": c * 1.01,
                    "low": o * 0.99,
                    "close": c,
                    "volume": 1e6,
                    "amount": 1e7,
                    "vwap": (o + c) / 2,
                    "data_version": "v1",
                }
            )
    by_m: dict[int, list] = {}
    for r in rows:
        by_m.setdefault(r["trading_date"].month, []).append(r)
    for month, mrows in by_m.items():
        write_market_daily(
            store,
            pa.Table.from_pylist(mrows),
            exchange="CN",
            year=2024,
            month=month,
            version="golden_4c",
            registry=registry,
        )
    return days


def seed_universes(store: LocalCanonicalStore, registry: LocalJsonRegistry) -> None:
    """两期 Universe：2020 含 AAA/BBB；2026 含 BBB/CCC（模拟成分变化）。"""
    for snap, version, members in [
        (SNAP_A, "2020", ["CNStock:AAA", "CNStock:BBB"]),
        (SNAP_B, "2026", ["CNStock:BBB", "CNStock:CCC"]),
    ]:
        rows = [
            {
                "universe_code": UNIVERSE,
                "universe_version": version,
                "instrument_key": ik,
                "valid_from": date(2020, 1, 1),
                "valid_to": None,
                "weight": 1.0,
                "member_rank": i + 1,
                "source_version": version,
                "snapshot_id": snap,
            }
            for i, ik in enumerate(members)
        ]
        written = write_universe_snapshot(
            store,
            pa.Table.from_pylist(rows),
            universe_code=UNIVERSE,
            universe_version=version,
            registry=registry,
        )
        registry.create_snapshot(
            snapshot_id=snap,
            name=snap,
            items=[
                {
                    "data_version_id": written.get("data_version_id") or 0,
                    "path": written.get("key") or "",
                    "checksum": written.get("checksum") or "",
                    "r2_uri": written.get("r2_uri") or "",
                }
            ],
        )


def seed_suspension(
    store: LocalCanonicalStore,
    registry: LocalJsonRegistry,
    days: list[date],
) -> date:
    """AAA 在第 3 个交易日停牌。"""
    sus_day = days[2]
    rows = []
    for d in days[:6]:
        for ik in INSTRUMENTS:
            rows.append(
                {
                    "instrument_key": ik,
                    "trading_date": d,
                    "status": "SUSPENDED" if (ik == "CNStock:AAA" and d == sus_day) else "NORMAL",
                    "is_suspended": bool(ik == "CNStock:AAA" and d == sus_day),
                    "is_limit_up": False,
                    "is_limit_down": False,
                    "upper_limit": None,
                    "lower_limit": None,
                    "data_version": "st1",
                }
            )
    write_trading_status(
        store,
        pa.Table.from_pylist(rows),
        exchange="CN",
        year=sus_day.year,
        month=sus_day.month,
        version="golden_st",
        registry=registry,
    )
    return sus_day


def register_factor_dataset(registry: LocalJsonRegistry, days: list[date]) -> FactorDatasetRecord:
    """登记最小 FactorDataset（值由 metadata 注入）。"""
    rec = FactorDatasetRecord(
        factor_dataset_id=FACTOR_DS_ID,
        factor_ref="momentum_20d@1.0.0",
        factor_hash="fh_golden_4c",
        dataset_hash="ds_golden_4c",
        snapshot_id=SNAP_A,
        universe_code=UNIVERSE,
        frequency="1d",
        start_date=days[0].isoformat(),
        end_date=days[10].isoformat(),
        storage_uri="memory://golden",
        checksum="abc",
        row_count=len(days) * 2,
        layout="long",
    )
    registry.upsert_factor_dataset(rec)
    return rec


def factor_records(days: list[date], *, include_ccc: bool = False) -> list[dict]:
    """因子值：AAA/BBB 每日有值；可选 CCC。"""
    rows = []
    for i, d in enumerate(days[:11]):
        rows.append(
            {
                "instrument_key": "CNStock:AAA",
                "factor_date": d,
                "factor_value": 0.1 + i * 0.01,
            }
        )
        rows.append(
            {
                "instrument_key": "CNStock:BBB",
                "factor_date": d,
                "factor_value": -0.05 + i * 0.01,
            }
        )
        if include_ccc:
            rows.append(
                {
                    "instrument_key": "CNStock:CCC",
                    "factor_date": d,
                    "factor_value": 0.0,
                }
            )
    # 一天缺失因子
    rows.append(
        {
            "instrument_key": "CNStock:AAA",
            "factor_date": days[11] if len(days) > 11 else days[-1],
            "factor_value": float("nan"),
        }
    )
    return rows


def make_env(tmp_path: Path):
    """构造评价环境。"""
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    query = DataQuery(store, registry)
    days = seed_market_handcrafted(store, registry)
    seed_universes(store, registry)
    sus_day = seed_suspension(store, registry, days)
    fds = register_factor_dataset(registry, days)
    svc = FactorEvaluationService(
        query,
        registry,
        store,
        artifact_store=EvaluationArtifactStore(root=tmp_path / "eval_art"),
    )
    return store, registry, query, svc, days, sus_day, fds


def default_spec(days: list[date], *, snapshot_id: str = SNAP_A) -> EvaluationSpec:
    """默认 next_open_to_close delay=1 horizons=[1,5]。"""
    return EvaluationSpec(
        factor_dataset_id=FACTOR_DS_ID,
        universe_code=UNIVERSE,
        universe_version="2020" if snapshot_id == SNAP_A else "2026",
        snapshot_id=snapshot_id,
        start_date=days[0].isoformat(),
        end_date=days[8].isoformat(),
        return_spec=ReturnSpec(
            definition="next_open_to_close",
            horizons=[1, 5],
            execution_delay=1,
        ),
        price_policy=PricePolicy(adjustment="none"),
        mode="CROSS_SECTIONAL",
    )
