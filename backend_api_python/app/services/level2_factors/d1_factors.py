"""Level2 日频因子读写 D1（经 Worker）。

表 ``l2_factors``：主键 ``(trade_date, symbol)``，列对齐 ``stored_columns()``。
日常增量用绑定参数多值 INSERT（每句最多 5 行）；历史迁移用字面量多行 INSERT 减写。
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Iterable

from . import d1_client
from .names import BASE_FACTORS, stored_columns

_log = logging.getLogger(__name__)

TABLE = "l2_factors"
# 19 列 / 100 绑定参数上限 → 每句最多 5 行（5×19=95）。
_BOUND_ROWS_PER_STATEMENT = 5
_MAX_BOUND_PARAMS = 100
# 字面量语句安全阈值（平台上限 100KB）。
_LITERAL_MAX_BYTES = 90_000

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
  trade_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  l2_spread REAL,
  l2_depth_bid REAL,
  l2_depth_ask REAL,
  l2_obi REAL,
  l2_ofi REAL,
  l2_order_ratio REAL,
  l2_active_net_buy REAL,
  l2_big_net_inflow_rate REAL,
  l2_cancel_ratio REAL,
  l2_auction_amount REAL,
  l2_auction_imbalance REAL,
  l2_ret_overnight REAL,
  l2_ret_open_30 REAL,
  l2_ret_tail_30 REAL,
  l2_ret_intraday REAL,
  l2_rv REAL,
  l2_rskew REAL,
  PRIMARY KEY (trade_date, symbol)
)
""".strip()

_INDEX_SQL = (
    f"CREATE INDEX IF NOT EXISTS idx_l2_factors_symbol_date "
    f"ON {TABLE} (symbol, trade_date)"
)


def ensure_schema() -> None:
    """幂等建表与索引。已有库缺 ``l2_ofi`` 时再补列，避免插入失败。"""
    d1_client.query(_SCHEMA_SQL)
    d1_client.query(_INDEX_SQL)
    _ensure_ofi_column()


def _ensure_ofi_column() -> None:
    """旧表补订单流列。

    D1 的 SQLite 不接受 ``ADD COLUMN IF NOT EXISTS``，会报 near EXISTS。
    先探测列，已有则不再 ALTER。
    """
    if _column_exists("l2_ofi"):
        return
    d1_client.query(f"ALTER TABLE {TABLE} ADD COLUMN l2_ofi REAL")


def _column_exists(column: str) -> bool:
    """用一次只读判断列是否存在。缺列是预期情况，其它错误继续抛出。"""
    try:
        # LIMIT 0 只做语法检查，不拉行。
        d1_client.query(f"SELECT {column} FROM {TABLE} LIMIT 0")
    except d1_client.D1WorkerError as exc:
        if "no such column" in str(exc):
            return False
        raise
    return True


def upsert_day(date: str, source: Path | Any) -> int:
    """把一日宽表写入 D1。``source`` 为 Parquet 路径或 DataFrame。返回行数。"""
    import pandas as pd

    if isinstance(source, (str, Path)):
        frame = pd.read_parquet(source)
    else:
        frame = source
    rows = dataframe_to_rows(frame, trade_date=str(date))
    upsert_rows(rows)
    return len(rows)


def upsert_rows(rows: list[dict[str, Any]]) -> None:
    """日常增量：绑定参数多值 INSERT ON CONFLICT。"""
    if not rows:
        return
    if not d1_client.configured():
        raise d1_client.D1WorkerError("D1 Worker 未配置")
    ensure_schema()
    columns = stored_columns()
    statements: list[dict[str, Any]] = []
    for chunk in _chunks(rows, _BOUND_ROWS_PER_STATEMENT):
        statements.append(_bound_upsert_statement(chunk, columns))
        if len(statements) >= d1_client.MAX_BATCH_STATEMENTS:
            d1_client.batch(statements)
            statements = []
    if statements:
        d1_client.batch(statements)


def upsert_rows_literal(rows: list[dict[str, Any]], *, max_bytes: int = _LITERAL_MAX_BYTES) -> int:
    """大批量字面量 INSERT OR REPLACE，经 Worker batch。返回语句数。"""
    statements_sql = rows_to_literal_insert_statements(rows, max_bytes=max_bytes)
    if not statements_sql:
        return 0
    if not d1_client.configured():
        raise d1_client.D1WorkerError("D1 Worker 未配置")
    ensure_schema()
    pending: list[dict[str, Any]] = []
    for sql in statements_sql:
        pending.append({"sql": sql, "params": []})
        if len(pending) >= d1_client.MAX_BATCH_STATEMENTS:
            d1_client.batch(pending)
            pending = []
    if pending:
        d1_client.batch(pending)
    return len(statements_sql)


def rows_to_literal_insert_statements(
    rows: Iterable[dict[str, Any]],
    *,
    max_bytes: int = _LITERAL_MAX_BYTES,
) -> list[str]:
    """把行打成尽量塞满的字面量 ``INSERT OR REPLACE`` 语句列表。"""
    columns = stored_columns()
    col_sql = ", ".join(columns)
    prefix = f"INSERT OR REPLACE INTO {TABLE} ({col_sql}) VALUES "
    prefix_size = len(prefix.encode("utf-8"))
    statements: list[str] = []
    values_parts: list[str] = []
    current_size = prefix_size

    for row in rows:
        tuple_sql = "(" + ", ".join(_sql_literal(row.get(col)) for col in columns) + ")"
        piece_size = len(tuple_sql.encode("utf-8")) + (2 if values_parts else 0)
        if values_parts and current_size + piece_size > max_bytes:
            statements.append(prefix + ", ".join(values_parts))
            values_parts = []
            current_size = prefix_size
            piece_size = len(tuple_sql.encode("utf-8"))
        values_parts.append(tuple_sql)
        current_size += piece_size
    if values_parts:
        statements.append(prefix + ", ".join(values_parts))
    return statements


def fetch_day(date: str) -> list[dict[str, Any]]:
    """读取某一交易日全部股票行。"""
    day = str(date)
    return d1_client.query(
        f"SELECT {', '.join(stored_columns())} FROM {TABLE} WHERE trade_date = ?",
        [day],
    )


def fetch_symbols(symbols: list[str], dates: list[str]) -> list[dict[str, Any]]:
    """按股票与交易日集合读取；自动切块避开绑定参数上限。"""
    codes = sorted({str(item).upper() for item in symbols if str(item).strip()})
    days = sorted({str(item) for item in dates if str(item).strip()})
    if not codes or not days:
        return []
    columns = ", ".join(stored_columns())
    rows: list[dict[str, Any]] = []
    # 预留：trade_date IN (?) 与 symbol IN (?) 共享 100 参数。
    for day_chunk in _chunk_by_budget(days, codes):
        day_ph = ", ".join("?" for _ in day_chunk)
        # 每个 day_chunk 再按 symbol 切，使 params <= 100。
        budget = _MAX_BOUND_PARAMS - len(day_chunk)
        for code_chunk in _chunks(codes, max(1, budget)):
            code_ph = ", ".join("?" for _ in code_chunk)
            sql = (
                f"SELECT {columns} FROM {TABLE} "
                f"WHERE trade_date IN ({day_ph}) AND symbol IN ({code_ph})"
            )
            rows.extend(d1_client.query(sql, [*day_chunk, *code_chunk]))
    return rows


def fetch_symbol_history(symbol: str, before: str, limit: int) -> list[dict[str, Any]]:
    """某股在 ``before`` 之前最近 ``limit`` 个交易日。"""
    code = str(symbol).upper()
    lim = max(0, int(limit))
    if lim <= 0:
        return []
    columns = ", ".join(stored_columns())
    return d1_client.query(
        f"SELECT {columns} FROM {TABLE} "
        f"WHERE symbol = ? AND trade_date < ? "
        f"ORDER BY trade_date DESC LIMIT ?",
        [code, str(before), lim],
    )


def warmup_dates(symbol: str, before: str, limit: int = 19) -> list[str]:
    """返回 ``before`` 之前最多 ``limit`` 个已有交易日（升序）。"""
    rows = fetch_symbol_history(symbol, before, limit)
    dates = [str(row["trade_date"]) for row in rows if row.get("trade_date")]
    return sorted(dates)


def count_day(date: str) -> int:
    """某日已有行数。未配置 Worker 时返回 0。"""
    if not d1_client.configured():
        return 0
    rows = d1_client.query(
        f"SELECT COUNT(*) AS n FROM {TABLE} WHERE trade_date = ?",
        [str(date)],
    )
    if not rows:
        return 0
    return int(rows[0].get("n") or 0)


def has_day(date: str, *, min_rows: int = 1) -> bool:
    """远端是否已有该日至少 ``min_rows`` 行。"""
    return count_day(date) >= max(1, int(min_rows))


def dataframe_to_rows(frame: Any, *, trade_date: str | None = None) -> list[dict[str, Any]]:
    """DataFrame → 行字典列表，只保留落盘列。"""
    import pandas as pd

    if frame is None or getattr(frame, "empty", True):
        return []
    columns = stored_columns()
    table = frame.copy()
    if "symbol" in table.columns:
        table["symbol"] = table["symbol"].astype(str).str.upper()
    if trade_date is not None:
        table["trade_date"] = str(trade_date)
    elif "trade_date" in table.columns:
        table["trade_date"] = table["trade_date"].astype(str)
    rows: list[dict[str, Any]] = []
    for record in table.to_dict(orient="records"):
        row = {column: _json_ready(record.get(column)) for column in columns}
        if not row.get("symbol") or not row.get("trade_date"):
            continue
        rows.append(row)
    return rows


def _bound_upsert_statement(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, Any]:
    placeholders = "(" + ", ".join("?" for _ in columns) + ")"
    values_sql = ", ".join(placeholders for _ in rows)
    updates = ", ".join(
        f"{column}=excluded.{column}"
        for column in columns
        if column not in {"trade_date", "symbol"}
    )
    sql = (
        f"INSERT INTO {TABLE} ({', '.join(columns)}) VALUES {values_sql} "
        f"ON CONFLICT(trade_date, symbol) DO UPDATE SET {updates}"
    )
    params: list[Any] = []
    for row in rows:
        for column in columns:
            params.append(_bind_value(row.get(column)))
    return {"sql": sql, "params": params}


def _bind_value(value: Any) -> Any:
    ready = _json_ready(value)
    if ready is None:
        return None
    return ready


def _json_ready(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return value


def _sql_literal(value: Any) -> str:
    ready = _json_ready(value)
    if ready is None:
        return "NULL"
    if isinstance(ready, bool):
        return "1" if ready else "0"
    if isinstance(ready, (int, float)):
        if isinstance(ready, float) and (math.isnan(ready) or math.isinf(ready)):
            return "NULL"
        return repr(float(ready)) if isinstance(ready, float) else str(int(ready))
    text = str(ready).replace("'", "''")
    return f"'{text}'"


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        return [items]
    return [items[index : index + size] for index in range(0, len(items), size)]


def _chunk_by_budget(days: list[str], codes: list[str]) -> list[list[str]]:
    """按 dates 切块，保证还能塞进至少一个 symbol 参数。"""
    if not days:
        return []
    # 至少留 1 个给 symbol。
    max_days = max(1, _MAX_BOUND_PARAMS - 1)
    # 若股票很多，进一步减小 day chunk，让一次能多塞股票。
    if len(codes) > 1:
        max_days = max(1, min(max_days, _MAX_BOUND_PARAMS // 2))
    return _chunks(days, max_days)


# 供测试断言列顺序与 BASE_FACTORS 一致。
FACTOR_COLUMNS = BASE_FACTORS
