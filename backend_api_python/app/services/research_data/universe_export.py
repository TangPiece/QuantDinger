"""从 PostgreSQL 业务 Universe 导出研究用 Canonical Snapshot。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

import pyarrow as pa

from app.services.universe import UniverseService, parse_as_of
from app.utils.db import get_db_connection

from .canonical_store import CanonicalStore
from .paths import snapshot_manifest_key
from .registry import ResearchRegistry, new_snapshot_id
from .schemas import SCHEMA_VERSION_UNIVERSE
from .writer import write_snapshot_manifest, write_universe_snapshot


def export_universe_snapshot(
    *,
    store: CanonicalStore,
    registry: ResearchRegistry,
    universe_code: str,
    universe_version: str,
    user_id: int = 1,
    start: date | str | None = None,
    end: date | str | None = None,
    snapshot_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """导出 PG membership → R2/local parquet + Registry snapshot。

    后续研究只能通过 DataQuery.universe(snapshot_id/universe_version) 读取。
    """
    svc = UniverseService()
    universe = _find_universe_by_code(user_id, universe_code)
    universe_id = int(universe["id"])
    start_date = parse_as_of(start) if start else date(1900, 1, 1)
    end_date = parse_as_of(end) if end else date.today()
    snap_id = snapshot_id or new_snapshot_id(f"univ_{universe_code}")

    rows = _load_membership_intervals(universe_id, start_date, end_date)
    if not rows:
        # 回退：as-of end 的点成员（watchlist / symbol_master）
        members = svc.resolve_members(user_id, universe_id, as_of=end_date)
        rows = [
            {
                "market": m["market"],
                "symbol": m["symbol"],
                "valid_from": start_date,
                "valid_to": None,
                "weight": m.get("weight"),
                "rank": m.get("rank"),
                "source_version": m.get("source_version") or "",
            }
            for m in members
        ]

    table = _rows_to_arrow(
        rows,
        universe_code=universe_code,
        universe_version=universe_version,
        snapshot_id=snap_id,
    )
    written = write_universe_snapshot(
        store,
        table,
        universe_code=universe_code,
        universe_version=universe_version,
        registry=registry,
    )
    item = {
        "dataset_code": f"universe_{universe_code}",
        "version": universe_version,
        "path": written["key"],
        "checksum": written["checksum"],
        "r2_uri": written["r2_uri"],
        "data_version_id": written.get("data_version_id"),
        "schema_version": SCHEMA_VERSION_UNIVERSE,
        "row_count": written["row_count"],
    }
    manifest_key = write_snapshot_manifest(
        store,
        snapshot_id=snap_id,
        items=[item],
        name=name or f"{universe_code}@{universe_version}",
        registry=registry,
        metadata={
            "universe_code": universe_code,
            "universe_version": universe_version,
            "pg_universe_id": universe_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    registry.upsert_universe_ref(
        universe_code=universe_code,
        pg_universe_id=universe_id,
        market=str(universe.get("market") or "") or None,
    )
    return {
        "snapshot_id": snap_id,
        "universe_code": universe_code,
        "universe_version": universe_version,
        "path": written["key"],
        "manifest_key": manifest_key or snapshot_manifest_key(snap_id),
        "checksum": written["checksum"],
        "row_count": written["row_count"],
        "pg_universe_id": universe_id,
    }


def _find_universe_by_code(user_id: int, code: str) -> dict[str, Any]:
    svc = UniverseService()
    for item in svc.list_universes(user_id):
        if str(item.get("code") or "") == code:
            return item
    raise KeyError(f"universe code not found or not visible: {code}")


def _load_membership_intervals(
    universe_id: int,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """直接读 interval 行，保留历史 valid_from/valid_to。"""
    with get_db_connection() as db:
        cur = db.cursor()
        cur.execute(
            """
            SELECT market, symbol, name, exchange_id, market_type,
                   instrument_id, settle_currency,
                   member_weight AS weight, member_rank AS rank,
                   valid_from, valid_to, source_version
            FROM qd_universe_members
            WHERE universe_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to > ?)
            ORDER BY market, symbol, valid_from
            """,
            (int(universe_id), end, start),
        )
        rows = cur.fetchall() or []
        cur.close()
    return [dict(r) for r in rows]


def _rows_to_arrow(
    rows: list[dict[str, Any]],
    *,
    universe_code: str,
    universe_version: str,
    snapshot_id: str,
) -> pa.Table:
    instrument_keys: list[str] = []
    valid_froms: list[date] = []
    valid_tos: list[Optional[date]] = []
    weights: list[Optional[float]] = []
    ranks: list[Optional[int]] = []
    source_versions: list[str] = []
    for row in rows:
        market = str(row.get("market") or "")
        symbol = str(row.get("symbol") or "")
        instrument_keys.append(f"{market}:{symbol}")
        vf = row.get("valid_from")
        if isinstance(vf, datetime):
            vf = vf.date()
        elif isinstance(vf, str):
            vf = date.fromisoformat(vf[:10])
        valid_froms.append(vf or date(1900, 1, 1))
        vt = row.get("valid_to")
        if isinstance(vt, datetime):
            vt = vt.date()
        elif isinstance(vt, str) and vt:
            vt = date.fromisoformat(vt[:10])
        elif not vt:
            vt = None
        valid_tos.append(vt)
        w = row.get("weight")
        weights.append(float(w) if w is not None else None)
        r = row.get("rank")
        ranks.append(int(r) if r is not None else None)
        source_versions.append(str(row.get("source_version") or ""))

    n = len(instrument_keys)
    return pa.table(
        {
            "universe_code": pa.array([universe_code] * n, type=pa.string()),
            "universe_version": pa.array([universe_version] * n, type=pa.string()),
            "instrument_key": pa.array(instrument_keys, type=pa.string()),
            "valid_from": pa.array(valid_froms, type=pa.date32()),
            "valid_to": pa.array(valid_tos, type=pa.date32()),
            "weight": pa.array(weights, type=pa.float64()),
            "member_rank": pa.array(ranks, type=pa.int32()),
            "source_version": pa.array(source_versions, type=pa.string()),
            "snapshot_id": pa.array([snapshot_id] * n, type=pa.string()),
        }
    )
