"""编排 cn_stock_daily@v1 Golden Dataset：ingest → snapshot → registry → dataset_hash。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Sequence

import pyarrow as pa

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import DatasetDefinition, PricePolicy
from app.services.research_data.hashing import compute_dataset_hash
from app.services.research_data.ingest.corporate_action import ingest_corporate_actions
from app.services.research_data.ingest.fundamental_pit import ingest_pit_fundamental
from app.services.research_data.ingest.market import ingest_market_daily
from app.services.research_data.ingest.trading_status import ingest_trading_status
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.writer import write_snapshot_manifest, write_universe_snapshot

GOLDEN_DATASET_CODE = "cn_stock_daily"
GOLDEN_DATASET_VERSION = "v1"
GOLDEN_DATASET_REF = f"{GOLDEN_DATASET_CODE}@{GOLDEN_DATASET_VERSION}"
DEFAULT_UNIVERSE_CODE = "CSI300"
DEFAULT_START = date(2020, 1, 1)
DEFAULT_END = date(2025, 12, 31)


def fixture_market_records(
    instrument_keys: Sequence[str],
    *,
    start: date,
    end: date,
    data_version: str,
) -> list[dict[str, Any]]:
    """CI 用确定性日线（不依赖外网）；覆盖 start..end 的每月首个交易日近似。"""
    records: list[dict[str, Any]] = []
    y, m = start.year, start.month
    day_i = 0
    while (y, m) <= (end.year, end.month):
        td = date(y, m, 1)
        if start <= td <= end:
            for j, ik in enumerate(instrument_keys):
                # 价格随月份缓慢上行，便于 post 复权对比
                base = 10.0 + j + day_i * 0.1
                records.append(
                    {
                        "instrument_key": ik,
                        "trading_date": td,
                        "open": base,
                        "high": base + 0.5,
                        "low": base - 0.5,
                        "close": base + 0.2,
                        "volume": 1000.0 + day_i,
                        "amount": (base + 0.2) * (1000.0 + day_i),
                        "vwap": base + 0.2,
                        "data_version": data_version,
                    }
                )
        day_i += 1
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return records


def fixture_universe_table(
    *,
    universe_code: str,
    universe_version: str,
    instrument_keys: Sequence[str],
    snapshot_id: str,
    valid_from: date,
    include_survivor_bias_rows: bool = True,
) -> pa.Table:
    """本地合成 CSI300 成分快照（CI 不连 PG）。

    核心成分 valid_from 使用传入值；默认附加幸存者偏差检验行：
    - CNStock:999999：valid_from=2020-01-01, valid_to=2023-12-31（历史成员）
    - CNStock:688001：valid_from=2024-04-01（后期调入）
    """
    # 核心成员从足够早的日期生效，便于历史 as_of 探测
    core_from = min(valid_from, date(2020, 1, 1))
    keys = list(instrument_keys)
    vfs = [core_from] * len(keys)
    vts: list[date | None] = [None] * len(keys)

    if include_survivor_bias_rows:
        # 历史调出：仅 knowledge_time <= 2023-12-31 可见
        if "CNStock:999999" not in keys:
            keys.append("CNStock:999999")
            vfs.append(date(2020, 1, 1))
            vts.append(date(2023, 12, 31))
        # 后期调入：仅 knowledge_time >= 2024-04-01 可见
        if "CNStock:688001" not in keys:
            keys.append("CNStock:688001")
            vfs.append(date(2024, 4, 1))
            vts.append(None)

    n = len(keys)
    return pa.table(
        {
            "universe_code": pa.array([universe_code] * n),
            "universe_version": pa.array([universe_version] * n),
            "instrument_key": pa.array(keys),
            "valid_from": pa.array(vfs, type=pa.date32()),
            "valid_to": pa.array(vts, type=pa.date32()),
            "weight": pa.array([1.0 / max(n, 1)] * n, type=pa.float64()),
            "member_rank": pa.array(list(range(1, n + 1)), type=pa.int32()),
            "source_version": pa.array(["fixture"] * n),
            "snapshot_id": pa.array([snapshot_id] * n),
        }
    )


def build_golden_dataset(
    store: CanonicalStore,
    registry: ResearchRegistry,
    *,
    instrument_keys: Sequence[str] | None = None,
    start: date = DEFAULT_START,
    end: date = DEFAULT_END,
    universe_code: str = DEFAULT_UNIVERSE_CODE,
    universe_version: str | None = None,
    snapshot_id: str | None = None,
    use_fixture: bool = True,
    market_records: Sequence[dict[str, Any]] | None = None,
    status: str = "validated",
) -> dict[str, Any]:
    """构建并登记 Golden Dataset `cn_stock_daily@v1`。

    Args:
        use_fixture: True 时用确定性合成数据（CI 默认）；False 时走 Source/PG。
        market_records: 可选注入日线行（覆盖 fixture/Source）。
        status: Registry dataset.status（默认 validated）。
    """
    instruments = list(
        instrument_keys
        or ["CNStock:000001", "CNStock:000002", "CNStock:600000"]
    )
    # fixture 幸存者成员也需要行情，避免物化后 D.features 全 NaN 日历行
    market_instruments = list(instruments)
    if use_fixture:
        for extra in ("CNStock:999999", "CNStock:688001"):
            if extra not in market_instruments:
                market_instruments.append(extra)

    uv = universe_version or f"golden-{date.today().isoformat()}"
    snap_id = snapshot_id or f"snap_cn_stock_daily_v1_{uv}"
    data_ver = GOLDEN_DATASET_VERSION

    # 1) Market
    if market_records is not None:
        market_meta = ingest_market_daily(
            store,
            instrument_keys=market_instruments,
            start=start,
            end=end,
            version=data_ver,
            registry=registry,
            preloaded_records=list(market_records),
        )
    elif use_fixture:
        market_meta = ingest_market_daily(
            store,
            instrument_keys=market_instruments,
            start=start,
            end=end,
            version=data_ver,
            registry=registry,
            preloaded_records=fixture_market_records(
                market_instruments, start=start, end=end, data_version=data_ver
            ),
        )
    else:
        market_meta = ingest_market_daily(
            store,
            instrument_keys=instruments,
            start=start,
            end=end,
            version=data_ver,
            registry=registry,
        )

    # Source 覆盖不足：截断到实际区间，不伪造
    actual_start = (
        date.fromisoformat(market_meta["actual_start"])
        if market_meta.get("actual_start")
        else start
    )
    actual_end = (
        date.fromisoformat(market_meta["actual_end"])
        if market_meta.get("actual_end")
        else end
    )

    # 2) PIT / CA / trading_status
    pit_meta = ingest_pit_fundamental(
        store,
        instrument_keys=market_instruments if use_fixture else instruments,
        version=data_ver,
        registry=registry,
        allow_synthetic=True,
    )
    ca_meta = ingest_corporate_actions(
        store,
        version=data_ver,
        registry=registry,
        instrument_keys=instruments,
        allow_synthetic=True,
    )
    status_meta = ingest_trading_status(
        store,
        version=data_ver,
        registry=registry,
        placeholder_year=actual_start.year,
        placeholder_month=actual_start.month,
    )

    # 3) Universe snapshot
    if use_fixture:
        univ_table = fixture_universe_table(
            universe_code=universe_code,
            universe_version=uv,
            instrument_keys=instruments,
            snapshot_id=snap_id,
            valid_from=actual_start,
        )
        univ_meta = write_universe_snapshot(
            store,
            univ_table,
            universe_code=universe_code,
            universe_version=uv,
            registry=registry,
        )
    else:
        from app.services.research_data.universe_export import export_universe_snapshot

        univ_meta = export_universe_snapshot(
            store=store,
            registry=registry,
            universe_code=universe_code,
            universe_version=uv,
            start=actual_start.isoformat(),
            end=actual_end.isoformat(),
        )

    # 4) Snapshot manifest items
    items: list[dict[str, Any]] = []
    for block in (market_meta.get("written") or []):
        items.append(
            {
                "dataset_code": "market_daily",
                "version": data_ver,
                "path": block["key"],
                "checksum": block["checksum"],
                "data_version_id": block.get("data_version_id"),
            }
        )
    for block in (pit_meta.get("written") or []):
        items.append(
            {
                "dataset_code": "pit_fundamental",
                "version": data_ver,
                "path": block["key"],
                "checksum": block["checksum"],
                "data_version_id": block.get("data_version_id"),
            }
        )
    for block in (ca_meta.get("written") or []):
        items.append(
            {
                "dataset_code": "corporate_action",
                "version": data_ver,
                "path": block["key"],
                "checksum": block["checksum"],
                "data_version_id": block.get("data_version_id"),
            }
        )
    for block in (status_meta.get("written") or []):
        items.append(
            {
                "dataset_code": "trading_status",
                "version": data_ver,
                "path": block["key"],
                "checksum": block["checksum"],
                "data_version_id": block.get("data_version_id"),
            }
        )
    univ_path = univ_meta.get("key") or univ_meta.get("path")
    items.append(
        {
            "dataset_code": f"universe_{universe_code}",
            "version": uv,
            "path": univ_path,
            "checksum": univ_meta.get("checksum"),
            "r2_uri": univ_meta.get("r2_uri") or univ_path,
            "data_version_id": univ_meta.get("data_version_id"),
        }
    )

    write_snapshot_manifest(
        store,
        snapshot_id=snap_id,
        items=items,
        name=f"{GOLDEN_DATASET_REF}",
        registry=registry,
        metadata={
            "requested_range": [start.isoformat(), end.isoformat()],
            "actual_range": [actual_start.isoformat(), actual_end.isoformat()],
            "truncated": market_meta.get("truncated"),
            "built_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # 5) DatasetDefinition + validated
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version=GOLDEN_DATASET_VERSION,
        name="CN Stock Daily Golden",
        frequency="1d",
        universe_code=universe_code,
        universe_version=uv,
        snapshot_id=snap_id,
        schema_version="market_bar_daily@1",
        features=["open", "high", "low", "close", "volume", "amount", "vwap"],
        price_policy=PricePolicy(adjustment="none", return_type="price"),
        pit=True,
    )
    registry.upsert_dataset(definition, status=status)
    handle = registry.get_dataset(GOLDEN_DATASET_REF)
    dataset_hash = handle.dataset_hash
    # 显式再算一遍写入报告，避免 Registry 漂移
    expected_hash = compute_dataset_hash(
        dataset_definition=definition.model_dump(mode="json"),
        dataset_version=definition.version,
        snapshot_id=definition.snapshot_id,
        schema_version=definition.schema_version,
        processor_version=definition.processor or "",
        materializer_version="none",
        price_policy=definition.price_policy.model_dump(mode="json"),
    )

    return {
        "dataset_ref": GOLDEN_DATASET_REF,
        "dataset_hash": dataset_hash,
        "expected_hash": expected_hash,
        "status": status,
        "snapshot_id": snap_id,
        "universe_code": universe_code,
        "universe_version": uv,
        "instrument_keys": instruments,
        "requested_range": [start.isoformat(), end.isoformat()],
        "actual_range": [actual_start.isoformat(), actual_end.isoformat()],
        "truncated": market_meta.get("truncated"),
        "market": market_meta,
        "pit": pit_meta,
        "corporate_action": ca_meta,
        "trading_status": status_meta,
        "universe": univ_meta,
        "items": items,
        "r2_paths": [it["path"] for it in items if it.get("path")],
    }


# 供脚本复用的辅助导出
__all__ = [
    "GOLDEN_DATASET_CODE",
    "GOLDEN_DATASET_VERSION",
    "GOLDEN_DATASET_REF",
    "build_golden_dataset",
    "fixture_market_records",
]
