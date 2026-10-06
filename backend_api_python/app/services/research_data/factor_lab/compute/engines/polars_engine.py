"""Polars/pandas 日频因子引擎（主路径）。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.research_data.factor_lab.compute.dsl import (
    DSLError,
    evaluate_on_market,
    frame_to_long_records,
)
from app.services.research_data.factor_lab.compute.protocol import ComputePlan, FactorFrame


class PolarsFactorEngine:
    """主引擎：DataQuery.market (+ optional fundamental) → DSL → FactorFrame。

    命名保留 Polars；当前数值路径用 pandas（与 DuckDB 易对齐）。若环境有 polars，
    可在后续将 evaluate 换为 polars 实现而不改 Domain。
    """

    name = "polars"

    def supports(self, factor, plan: ComputePlan) -> bool:
        return plan.engine in ("polars", "quantdinger")

    def compute(self, plan: ComputePlan, *, query, registry) -> FactorFrame:
        code, version = plan.factor_ref.split("@", 1)
        start = date.fromisoformat(plan.start_date[:10])
        end = date.fromisoformat(plan.end_date[:10])

        # universe instruments（可选）
        instruments = self._instruments(query, plan)
        market = query.market(
            instruments,
            start,
            end,
            frequency="1d",
            price_policy=plan.price_policy,
            exchange=plan.metadata.get("exchange", "CN") if plan.metadata else "CN",
        )
        if market is None or market.empty:
            return FactorFrame.from_records([])

        expr = plan.expression
        # PIT fundamental：表达式为 metric 名或 roe 等
        if plan.information_policy == "PIT_SAFE" or any(
            x.startswith("fundamental:") for x in plan.dependency_order
        ):
            return self._compute_fundamental(plan, query, market, code, version)

        try:
            values = evaluate_on_market(market, expr)
        except DSLError:
            # 回退：若表达式是列名
            if expr.lower() in {c.lower() for c in market.columns}:
                values = market[expr]
            else:
                raise
        records = frame_to_long_records(
            market, values, factor_code=code, factor_version=version
        )
        return FactorFrame.from_records(records, layout="long")

    def _compute_fundamental(
        self, plan: ComputePlan, query, market: pd.DataFrame, code: str, version: str
    ) -> FactorFrame:
        """fundamental 依赖：按 knowledge_time 取 PIT，再 asof merge 到交易日。"""
        metric = "roe"
        for node in plan.dependency_order:
            if node.startswith("fundamental:"):
                metric = node.split(":", 1)[1]
                break
        # 表达式可覆盖 metric
        if plan.expression and plan.expression.lower() not in (
            "momentum_20",
            "volatility_20",
        ):
            if re_metric := plan.expression.strip():
                if " " not in re_metric and "/" not in re_metric and "(" not in re_metric:
                    metric = re_metric

        instruments = sorted(market["instrument_key"].astype(str).unique().tolist())
        fund = query.fundamental(
            instruments,
            [metric],
            plan.knowledge_time,
            exchange=plan.metadata.get("exchange", "CN") if plan.metadata else "CN",
        )
        if fund is None or fund.empty:
            return FactorFrame.from_records([])

        # 仅保留 available_time <= knowledge_time（DataQuery 已过滤）；防御再滤
        fund = fund.copy()
        if "available_time" in fund.columns:
            kt = pd.Timestamp(plan.knowledge_time)
            if kt.tzinfo is None:
                kt = kt.tz_localize("UTC")
            at = pd.to_datetime(fund["available_time"], utc=True)
            fund = fund.loc[at <= kt]
        if fund.empty:
            return FactorFrame.from_records([])

        # 取每标的最新 revision
        fund = fund.sort_values(["instrument_key", "available_time", "revision"])
        latest = fund.groupby("instrument_key", as_index=False).tail(1)
        value_col = "value" if "value" in latest.columns else metric
        records = []
        # 广播到每个交易日（截面快照因子）
        mkt = market.copy()
        mkt["trading_date"] = pd.to_datetime(mkt["trading_date"]).dt.strftime("%Y-%m-%d")
        val_map = {
            str(r["instrument_key"]): float(r[value_col])
            for _, r in latest.iterrows()
            if pd.notna(r[value_col])
        }
        for _, row in mkt.iterrows():
            ik = str(row["instrument_key"])
            if ik not in val_map:
                continue
            records.append(
                {
                    "instrument_key": ik,
                    "trading_date": row["trading_date"],
                    "factor_code": code,
                    "factor_version": version,
                    "value": val_map[ik],
                }
            )
        return FactorFrame.from_records(records, layout="long")

    def _instruments(self, query, plan: ComputePlan) -> list[str]:
        meta = plan.metadata or {}
        if meta.get("instruments") or meta.get("instrument_keys"):
            return list(meta.get("instruments") or meta.get("instrument_keys") or [])
        if plan.universe_code:
            try:
                keys = query.universe(
                    plan.universe_code,
                    plan.knowledge_time,
                    snapshot_id=plan.snapshot_id,
                )
                if keys:
                    return sorted(str(k) for k in keys)
            except Exception:
                pass
        return []
