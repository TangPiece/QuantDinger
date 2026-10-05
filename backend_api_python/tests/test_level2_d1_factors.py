"""D1 因子打包：绑定参数 5 行/句、字面量按字节切块、NaN→NULL。"""
from __future__ import annotations

import math

import pandas as pd

from app.services.level2_factors import d1_factors
from app.services.level2_factors.names import stored_columns


def _row(symbol: str, day: str = "20251009", **overrides):
    base = {column: 0.1 for column in stored_columns()}
    base["trade_date"] = day
    base["symbol"] = symbol
    base.update(overrides)
    return base


def test_bound_upsert_chunks_five_rows(monkeypatch):
    seen: list[list] = []

    def fake_batch(statements):
        seen.append(statements)
        return []

    monkeypatch.setattr(d1_factors.d1_client, "configured", lambda: True)
    monkeypatch.setattr(d1_factors.d1_client, "query", lambda *a, **k: [])
    monkeypatch.setattr(d1_factors.d1_client, "batch", fake_batch)
    monkeypatch.setattr(d1_factors, "ensure_schema", lambda: None)

    rows = [_row(f"{i:06d}.SH") for i in range(12)]
    d1_factors.upsert_rows(rows)
    # 12 行 → 3 句（5+5+2），一次 batch。
    assert len(seen) == 1
    assert len(seen[0]) == 3
    assert seen[0][0]["sql"].count("?") == 5 * len(stored_columns())
    assert seen[0][2]["sql"].count("?") == 2 * len(stored_columns())


def test_nan_becomes_null_in_bound_params(monkeypatch):
    captured = []

    monkeypatch.setattr(d1_factors.d1_client, "configured", lambda: True)
    monkeypatch.setattr(d1_factors.d1_client, "query", lambda *a, **k: [])
    monkeypatch.setattr(d1_factors.d1_client, "batch", lambda stmts: captured.extend(stmts) or [])
    monkeypatch.setattr(d1_factors, "ensure_schema", lambda: None)

    d1_factors.upsert_rows([_row("600519.SH", l2_obi=float("nan"), l2_rv=math.inf)])
    params = captured[0]["params"]
    columns = stored_columns()
    assert params[columns.index("l2_obi")] is None
    assert params[columns.index("l2_rv")] is None


def test_literal_statements_pack_many_rows_under_byte_limit():
    rows = [_row(f"{i:06d}.SH", l2_obi=0.123456) for i in range(200)]
    statements = d1_factors.rows_to_literal_insert_statements(rows, max_bytes=5_000)
    assert len(statements) >= 2
    packed = 0
    for sql in statements:
        assert len(sql.encode("utf-8")) <= 5_000
        assert sql.startswith("INSERT OR REPLACE")
        rows_in_stmt = sql.count("), (") + 1
        packed += rows_in_stmt
        # 每句应远多于绑定路径的 5 行。
        assert rows_in_stmt > 5
    assert packed == 200


def test_literal_nan_is_null():
    sql = d1_factors.rows_to_literal_insert_statements(
        [_row("600519.SH", l2_obi=float("nan"))]
    )[0]
    assert "NULL" in sql


def test_dataframe_to_rows_drops_rollups():
    frame = pd.DataFrame([{
        "trade_date": "20251009",
        "symbol": "600519.SH",
        "l2_obi": 0.2,
        "l2_obi_mean_5": 0.1,
    }])
    rows = d1_factors.dataframe_to_rows(frame)
    assert len(rows) == 1
    assert "l2_obi_mean_5" not in rows[0]
    assert set(rows[0]) == set(stored_columns())


def test_fetch_symbols_chunks_params(monkeypatch):
    calls = []

    def fake_query(sql, params=None):
        calls.append(list(params or []))
        return []

    monkeypatch.setattr(d1_factors.d1_client, "query", fake_query)
    symbols = [f"{i:06d}.SH" for i in range(80)]
    dates = [f"20251{i:03d}" for i in range(40)]
    d1_factors.fetch_symbols(symbols, dates)
    assert calls
    assert all(len(params) <= 100 for params in calls)


def test_ensure_schema_adds_missing_ofi_column(monkeypatch):
    calls = []

    def fake_query(sql, params=None):
        calls.append(sql)
        if sql.startswith("SELECT l2_ofi"):
            raise d1_factors.d1_client.D1WorkerError("D1_ERROR: no such column: l2_ofi")
        return []

    monkeypatch.setattr(d1_factors.d1_client, "query", fake_query)
    d1_factors.ensure_schema()
    alters = [sql for sql in calls if sql.upper().startswith("ALTER")]
    assert alters == ["ALTER TABLE l2_factors ADD COLUMN l2_ofi REAL"]


def test_ensure_schema_skips_alter_when_ofi_exists(monkeypatch):
    calls = []
    monkeypatch.setattr(d1_factors.d1_client, "query", lambda sql, params=None: calls.append(sql) or [])
    d1_factors.ensure_schema()
    assert not any(sql.upper().startswith("ALTER") for sql in calls)


def test_upsert_day_reads_parquet(tmp_path, monkeypatch):
    monkeypatch.setattr(d1_factors.d1_client, "configured", lambda: True)
    monkeypatch.setattr(d1_factors, "ensure_schema", lambda: None)
    seen = []
    monkeypatch.setattr(d1_factors, "upsert_rows", lambda rows: seen.append(rows))

    path = tmp_path / "20251009.parquet"
    pd.DataFrame([_row("600519.SH"), _row("000001.SZ")]).to_parquet(path, index=False)
    assert d1_factors.upsert_day("20251009", path) == 2
    assert len(seen[0]) == 2
