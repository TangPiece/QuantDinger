"""DuckDB 日频因子引擎（SQL window；与 Polars Golden 对齐）。"""

from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd

from app.services.research_data.factor_lab.compute.protocol import ComputePlan, FactorFrame


class DuckDBFactorEngine:
    """对 market DataFrame 跑简单 SQL：momentum / volatility。"""

    name = "duckdb"

    def supports(self, factor, plan: ComputePlan) -> bool:
        return plan.engine == "duckdb"

    def compute(self, plan: ComputePlan, *, query, registry) -> FactorFrame:
        code, version = plan.factor_ref.split("@", 1)
        meta = plan.metadata or {}
        instruments = list(meta.get("instruments") or meta.get("instrument_keys") or [])
        if not instruments and plan.universe_code:
            try:
                instruments = list(
                    query.universe(
                        plan.universe_code,
                        plan.knowledge_time,
                        snapshot_id=plan.snapshot_id,
                    )
                )
            except Exception:
                instruments = []
        start = date.fromisoformat(plan.start_date[:10])
        end = date.fromisoformat(plan.end_date[:10])
        market = query.market(
            instruments,
            start,
            end,
            frequency="1d",
            price_policy=plan.price_policy,
            exchange=meta.get("exchange", "CN"),
        )
        if market is None or market.empty:
            return FactorFrame.from_records([])

        expr = (plan.expression or "").strip().lower()
        con = duckdb.connect(database=":memory:")
        con.register("mkt", market)
        if expr.startswith("momentum_") or expr.startswith("pct_change_"):
            n = int(expr.split("_")[-1])
            sql = f"""
            SELECT instrument_key, trading_date,
                   close / lag(close, {n}) OVER (
                     PARTITION BY instrument_key ORDER BY trading_date
                   ) - 1.0 AS value
            FROM mkt
            """
        elif expr.startswith("volatility_"):
            n = int(expr.split("_")[-1])
            sql = f"""
            SELECT instrument_key, trading_date,
                   stddev_samp(ret) OVER (
                     PARTITION BY instrument_key ORDER BY trading_date
                     ROWS BETWEEN {n - 1} PRECEDING AND CURRENT ROW
                   ) AS value
            FROM (
              SELECT instrument_key, trading_date, close,
                     close / lag(close, 1) OVER (
                       PARTITION BY instrument_key ORDER BY trading_date
                     ) - 1.0 AS ret
              FROM mkt
            ) t
            """
        else:
            # 默认动量 20
            sql = """
            SELECT instrument_key, trading_date,
                   close / lag(close, 20) OVER (
                     PARTITION BY instrument_key ORDER BY trading_date
                   ) - 1.0 AS value
            FROM mkt
            """
        out = con.execute(sql).df()
        con.close()
        records = []
        for _, row in out.iterrows():
            if pd.isna(row["value"]):
                continue
            td = row["trading_date"]
            day = td.date().isoformat() if hasattr(td, "date") else str(td)[:10]
            records.append(
                {
                    "instrument_key": str(row["instrument_key"]),
                    "trading_date": day,
                    "factor_code": code,
                    "factor_version": version,
                    "value": float(row["value"]),
                }
            )
        return FactorFrame.from_records(records, layout="long")
