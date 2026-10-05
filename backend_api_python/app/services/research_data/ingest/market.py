"""日线 Source → Canonical market（写 raw OHLCV，不写复权价）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Sequence

import pyarrow as pa

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.writer import write_market_daily


def instrument_to_cn_symbol(instrument_key: str) -> str:
    """CNStock:000001 → 000001。"""
    if ":" in instrument_key:
        return instrument_key.split(":", 1)[1]
    return instrument_key


def kline_rows_to_records(
    instrument_key: str,
    rows: Sequence[dict[str, Any]],
    *,
    data_version: str,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    """将 DataSource get_kline 行转为 Canonical market 行（raw）。"""
    out: list[dict[str, Any]] = []
    for row in rows:
        ts = row.get("timestamp") or row.get("time") or row.get("t")
        if ts is None:
            continue
        # 毫秒/秒时间戳兼容
        ts_i = int(ts)
        if ts_i > 10_000_000_000:
            ts_i = ts_i // 1000
        trading_date = datetime.fromtimestamp(ts_i, tz=timezone.utc).date()
        if start and trading_date < start:
            continue
        if end and trading_date > end:
            continue
        open_ = float(row.get("open") or row.get("o") or 0.0)
        high = float(row.get("high") or row.get("h") or 0.0)
        low = float(row.get("low") or row.get("l") or 0.0)
        close = float(row.get("close") or row.get("c") or 0.0)
        volume = float(row.get("volume") or row.get("v") or 0.0)
        amount = float(row.get("amount") or row.get("turnover") or 0.0)
        vwap = (amount / volume) if volume else close
        out.append(
            {
                "instrument_key": instrument_key,
                "trading_date": trading_date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": amount,
                "vwap": vwap,
                "data_version": data_version,
            }
        )
    return out


def records_to_market_table(records: Sequence[dict[str, Any]]) -> pa.Table:
    """行列表 → Arrow market_bar_daily 表（稳定列序）。"""
    if not records:
        return pa.table(
            {
                "instrument_key": pa.array([], type=pa.string()),
                "trading_date": pa.array([], type=pa.date32()),
                "open": pa.array([], type=pa.float64()),
                "high": pa.array([], type=pa.float64()),
                "low": pa.array([], type=pa.float64()),
                "close": pa.array([], type=pa.float64()),
                "volume": pa.array([], type=pa.float64()),
                "amount": pa.array([], type=pa.float64()),
                "vwap": pa.array([], type=pa.float64()),
                "data_version": pa.array([], type=pa.string()),
            }
        )
    # 稳定排序，保证 determinism
    ordered = sorted(records, key=lambda r: (r["instrument_key"], r["trading_date"]))
    return pa.table(
        {
            "instrument_key": [r["instrument_key"] for r in ordered],
            "trading_date": pa.array([r["trading_date"] for r in ordered], type=pa.date32()),
            "open": [float(r["open"]) for r in ordered],
            "high": [float(r["high"]) for r in ordered],
            "low": [float(r["low"]) for r in ordered],
            "close": [float(r["close"]) for r in ordered],
            "volume": [float(r["volume"]) for r in ordered],
            "amount": [float(r["amount"]) for r in ordered],
            "vwap": [float(r["vwap"]) for r in ordered],
            "data_version": [r["data_version"] for r in ordered],
        }
    )


def default_fetch_kline(instrument_key: str, *, limit: int = 3000) -> list[dict[str, Any]]:
    """经 DataSourceFactory 拉 CN 日线；仅 ingest 可调用。"""
    from app.data_sources.factory import DataSourceFactory

    symbol = instrument_to_cn_symbol(instrument_key)
    return DataSourceFactory.get_kline(
        market="CNStock",
        symbol=symbol,
        timeframe="1D",
        limit=limit,
    )


def ingest_market_daily(
    store: CanonicalStore,
    *,
    instrument_keys: Iterable[str],
    start: date,
    end: date,
    version: str,
    registry: ResearchRegistry | None = None,
    exchange: str = "CN",
    fetch_kline: Callable[..., list[dict[str, Any]]] | None = None,
    preloaded_records: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """拉取（或注入）日线并按年月分区写入 Canonical。

    Args:
        fetch_kline: 可注入的拉数函数，便于单测/fixture；默认走 Source。
        preloaded_records: 若提供则跳过 Source，直接写（CI fixture）。
    """
    fetcher = fetch_kline or default_fetch_kline
    records: list[dict[str, Any]] = list(preloaded_records or [])
    source_errors: list[str] = []
    if preloaded_records is None:
        for ik in instrument_keys:
            try:
                rows = fetcher(ik, limit=5000)
                records.extend(
                    kline_rows_to_records(
                        ik, rows, data_version=version, start=start, end=end
                    )
                )
            except Exception as exc:  # noqa: BLE001 — ingest 聚合错误写入报告
                source_errors.append(f"{ik}: {exc}")

    # 截断到可用区间（不伪造）
    if records:
        dates = [r["trading_date"] for r in records]
        actual_start = min(dates)
        actual_end = max(dates)
    else:
        actual_start = None
        actual_end = None

    by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        td: date = rec["trading_date"]
        by_ym[(td.year, td.month)].append(rec)

    written: list[dict[str, Any]] = []
    for (year, month), part_rows in sorted(by_ym.items()):
        table = records_to_market_table(part_rows)
        meta = write_market_daily(
            store,
            table,
            exchange=exchange,
            year=year,
            month=month,
            registry=registry,
            version=version,
        )
        written.append(meta)

    return {
        "written": written,
        "row_count": len(records),
        "actual_start": actual_start.isoformat() if actual_start else None,
        "actual_end": actual_end.isoformat() if actual_end else None,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "source_errors": source_errors,
        "truncated": bool(
            actual_start
            and actual_end
            and (actual_start > start or actual_end < end)
        ),
    }
