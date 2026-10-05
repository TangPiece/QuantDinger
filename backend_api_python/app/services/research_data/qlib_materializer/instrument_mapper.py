"""QuantDinger InstrumentKey → Qlib instrument 稳定映射。"""

from __future__ import annotations

from datetime import date
from typing import Any, Sequence

import pyarrow as pa


class InstrumentMappingError(ValueError):
    """无法映射的标的。"""


def to_qlib_instrument(instrument_key: str) -> str:
    """CNStock:600000 → SH600000；CNStock:000001 → SZ000001。

    规则（A 股惯例）：6 开头上交所 SH，其余深交所 SZ。
    其它 market 本阶段显式报错（不 silently 编造）。
    """
    text = str(instrument_key or "").strip()
    if ":" not in text:
        raise InstrumentMappingError(f"invalid instrument_key: {instrument_key!r}")
    market, symbol = text.split(":", 1)
    code = symbol.strip().upper()
    if market == "CNStock":
        if not code.isdigit() or len(code) != 6:
            raise InstrumentMappingError(f"unsupported CNStock symbol: {symbol!r}")
        prefix = "SH" if code.startswith("6") else "SZ"
        return f"{prefix}{code}"
    raise InstrumentMappingError(f"unsupported market for Qlib mapping: {market}")


def exchange_of_qlib(qlib_instrument: str) -> str:
    """SH600000 → SSE；SZ000001 → SZSE。"""
    if qlib_instrument.startswith("SH"):
        return "SSE"
    if qlib_instrument.startswith("SZ"):
        return "SZSE"
    return ""


def build_mapping_rows(
    instrument_keys: Sequence[str],
    *,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> list[dict[str, Any]]:
    """生成 instrument_mapping 行。"""
    rows: list[dict[str, Any]] = []
    for ik in instrument_keys:
        qlib_id = to_qlib_instrument(ik)
        _, symbol = ik.split(":", 1)
        rows.append(
            {
                "instrument_key": ik,
                "qlib_instrument": qlib_id,
                "exchange": exchange_of_qlib(qlib_id),
                "symbol": symbol,
                "valid_from": valid_from,
                "valid_to": valid_to,
            }
        )
    return sorted(rows, key=lambda r: r["instrument_key"])


def write_instrument_mapping_parquet(path, rows: Sequence[dict[str, Any]]) -> None:
    """写入 metadata/instrument_mapping.parquet。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        table = pa.table(
            {
                "instrument_key": pa.array([], type=pa.string()),
                "qlib_instrument": pa.array([], type=pa.string()),
                "exchange": pa.array([], type=pa.string()),
                "symbol": pa.array([], type=pa.string()),
                "valid_from": pa.array([], type=pa.date32()),
                "valid_to": pa.array([], type=pa.date32()),
            }
        )
    else:
        table = pa.table(
            {
                "instrument_key": [r["instrument_key"] for r in rows],
                "qlib_instrument": [r["qlib_instrument"] for r in rows],
                "exchange": [r["exchange"] for r in rows],
                "symbol": [r["symbol"] for r in rows],
                "valid_from": pa.array([r.get("valid_from") for r in rows], type=pa.date32()),
                "valid_to": pa.array([r.get("valid_to") for r in rows], type=pa.date32()),
            }
        )
    import pyarrow.parquet as pq

    pq.write_table(table, path, compression="zstd")
