"""Level2 日频因子的本地 SQLite 读缓存（D1 的临时副本）。

图表/回测 ``enrich_panel`` 先查这里，缺口再打 Worker；只写入有行结果。
容量用 ``LEVEL2_FACTOR_CACHE_MAX_MB`` / ``MAX_DAYS`` 约束（默认约三年、2GB）。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .factor_cache import cutoff_date, dates_to_evict, factor_limit_bytes, factor_max_days
from .names import stored_columns

_log = logging.getLogger(__name__)
_TABLE = "l2_factor_local"
_LOCK = threading.RLock()
_SCHEMA_READY: set[str] = set()


def cache_path() -> Path:
    """SQLite 文件路径；``LEVEL2_D1_CACHE_PATH`` 可覆盖默认位置。"""
    raw = os.getenv("LEVEL2_D1_CACHE_PATH", "").strip()
    if raw:
        path = Path(raw)
    else:
        path = Path(__file__).resolve().parents[3] / "data" / "level2_d1_cache.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fetch(symbols: list[str], dates: list[str]) -> list[dict[str, Any]]:
    """按股票与交易日读取本地缓存行。"""
    codes = sorted({str(item).upper() for item in symbols if str(item).strip()})
    days = sorted({str(item) for item in dates if str(item).strip()})
    if not codes or not days:
        return []
    columns = stored_columns()
    placeholders_days = ", ".join("?" for _ in days)
    placeholders_codes = ", ".join("?" for _ in codes)
    sql = (
        f"SELECT {', '.join(columns)} FROM {_TABLE} "
        f"WHERE trade_date IN ({placeholders_days}) AND symbol IN ({placeholders_codes})"
    )
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            rows = conn.execute(sql, [*days, *codes]).fetchall()
            now = _now()
            # 命中时刷新访问时间，便于同日 LRU（按交易日淘汰时仍以日期为主）。
            if rows:
                conn.executemany(
                    f"UPDATE {_TABLE} SET accessed_at = ? WHERE trade_date = ? AND symbol = ?",
                    [(now, str(row["trade_date"]), str(row["symbol"]).upper()) for row in rows],
                )
                conn.commit()
            return [_row_to_dict(row, columns) for row in rows]
    except Exception:
        _log.warning("Level2 本地 SQLite 读取失败", exc_info=True)
        return []


def upsert_rows(rows: list[dict[str, Any]]) -> None:
    """写入有行结果；空列表忽略。写入后按容量策略淘汰。"""
    if not rows:
        return
    columns = stored_columns()
    keep = max((str(row.get("trade_date") or "") for row in rows), default="")
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            now = _now()
            for row in rows:
                day = str(row.get("trade_date") or "").strip()
                code = str(row.get("symbol") or "").strip().upper()
                if not day or not code:
                    continue
                values = [_cell(row.get(column)) for column in columns]
                # trade_date / symbol 用规范化后的值覆盖。
                values[0] = day
                values[1] = code
                payload = {column: values[index] for index, column in enumerate(columns)}
                size = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
                placeholders = ", ".join("?" for _ in columns)
                updates = ", ".join(
                    f"{column}=excluded.{column}" for column in columns if column not in {"trade_date", "symbol"}
                )
                sql = (
                    f"INSERT INTO {_TABLE} ({', '.join(columns)}, bytes, accessed_at) "
                    f"VALUES ({placeholders}, ?, ?) "
                    f"ON CONFLICT(trade_date, symbol) DO UPDATE SET {updates}, "
                    f"bytes=excluded.bytes, accessed_at=excluded.accessed_at"
                )
                conn.execute(sql, [*values, size, now])
            conn.commit()
            _enforce_conn(conn, keep_date=keep or now[:8].replace("-", ""))
            conn.commit()
    except Exception:
        _log.warning("Level2 本地 SQLite 写入失败", exc_info=True)


def warmup_dates(symbol: str, before: str, limit: int = 19) -> list[str]:
    """本地该股在 ``before`` 之前最近 ``limit`` 个交易日（升序）。"""
    code = str(symbol).upper()
    lim = max(0, int(limit))
    if not code or lim <= 0:
        return []
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            rows = conn.execute(
                f"SELECT trade_date FROM {_TABLE} "
                f"WHERE symbol = ? AND trade_date < ? "
                f"ORDER BY trade_date DESC LIMIT ?",
                [code, str(before), lim],
            ).fetchall()
            return sorted(str(row["trade_date"]) for row in rows if row["trade_date"])
    except Exception:
        _log.warning("Level2 本地预热日期查询失败 %s", code, exc_info=True)
        return []


def invalidate(symbols: Iterable[str] | None = None, dates: Iterable[str] | None = None) -> None:
    """按股票和/或交易日删除本地行；两边都空则清空整表。"""
    codes = sorted({str(item).upper() for item in (symbols or []) if str(item).strip()})
    days = sorted({str(item) for item in (dates or []) if str(item).strip()})
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            if not codes and not days:
                conn.execute(f"DELETE FROM {_TABLE}")
            elif codes and days:
                conn.execute(
                    f"DELETE FROM {_TABLE} WHERE symbol IN ({', '.join('?' for _ in codes)}) "
                    f"AND trade_date IN ({', '.join('?' for _ in days)})",
                    [*codes, *days],
                )
            elif codes:
                conn.execute(
                    f"DELETE FROM {_TABLE} WHERE symbol IN ({', '.join('?' for _ in codes)})",
                    codes,
                )
            else:
                conn.execute(
                    f"DELETE FROM {_TABLE} WHERE trade_date IN ({', '.join('?' for _ in days)})",
                    days,
                )
            conn.commit()
    except Exception:
        _log.warning("Level2 本地 SQLite invalidate 失败", exc_info=True)


def enforce(keep_date: str = "") -> None:
    """按天数与容量淘汰；供测试或外部主动触发。"""
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            _enforce_conn(conn, keep_date=str(keep_date or ""))
            conn.commit()
    except Exception:
        _log.warning("Level2 本地 SQLite 淘汰失败", exc_info=True)


def reset_for_tests() -> None:
    """单测切换缓存路径后清掉 schema 缓存标记。"""
    _SCHEMA_READY.clear()


def _enforce_conn(conn: sqlite3.Connection, *, keep_date: str) -> None:
    """先删过期交易日，再按 SUM(bytes) 从最老日期删到上限以下。"""
    sizes = {
        str(row["trade_date"]): int(row["total"] or 0)
        for row in conn.execute(
            f"SELECT trade_date, COALESCE(SUM(bytes), 0) AS total FROM {_TABLE} GROUP BY trade_date"
        )
    }
    if not sizes:
        return
    victims = dates_to_evict(
        list(sizes),
        sizes,
        cutoff=cutoff_date(factor_max_days()),
        limit=factor_limit_bytes(),
        keep=str(keep_date or max(sizes)),
    )
    if not victims:
        return
    conn.execute(
        f"DELETE FROM {_TABLE} WHERE trade_date IN ({', '.join('?' for _ in victims)})",
        list(victims),
    )


def _connect() -> sqlite3.Connection:
    path = cache_path()
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    key = str(cache_path())
    if key in _SCHEMA_READY:
        return
    with _LOCK:
        if key in _SCHEMA_READY:
            return
        columns = stored_columns()
        defs = ["trade_date TEXT NOT NULL", "symbol TEXT NOT NULL"]
        for column in columns:
            if column in {"trade_date", "symbol"}:
                continue
            defs.append(f"{column} REAL")
        defs.append("bytes INTEGER NOT NULL DEFAULT 0")
        defs.append("accessed_at TEXT NOT NULL DEFAULT ''")
        defs.append("PRIMARY KEY (trade_date, symbol)")
        conn.execute(f"CREATE TABLE IF NOT EXISTS {_TABLE} ({', '.join(defs)})")
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_symbol_date "
            f"ON {_TABLE} (symbol, trade_date)"
        )
        # 旧缓存库是按当时的列建的，新因子补列后才能按 stored_columns 读取。
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({_TABLE})")}
        for column in columns:
            if column not in existing:
                conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {column} REAL")
        conn.commit()
        _SCHEMA_READY.add(key)


def _row_to_dict(row: sqlite3.Row, columns: list[str]) -> dict[str, Any]:
    return {column: row[column] for column in columns if column in row.keys()}


def _cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes, bool)):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and value != value:
        return None
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
