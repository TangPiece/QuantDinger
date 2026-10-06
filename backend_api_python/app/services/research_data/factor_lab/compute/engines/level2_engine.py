"""Level2 薄适配：复用 enrich_panel / 注入面板，不改 Worker。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.research_data.factor_lab.compute.protocol import ComputePlan, FactorFrame


class Level2FactorEngine:
    """将 Level2 日频列映射为统一 FactorFrame。"""

    name = "level2"

    def supports(self, factor, plan: ComputePlan) -> bool:
        return plan.engine == "level2"

    def compute(self, plan: ComputePlan, *, query, registry) -> FactorFrame:
        code, version = plan.factor_ref.split("@", 1)
        meta = plan.metadata or {}
        # 测试注入：l2_panel DataFrame
        panel = meta.get("l2_panel")
        if panel is None:
            panel = self._load_panel(plan, query)
        if panel is None or (hasattr(panel, "empty") and panel.empty):
            return FactorFrame.from_records([])

        df = panel if isinstance(panel, pd.DataFrame) else pd.DataFrame(panel)
        # 列名：优先 expression，其次常见 l2_* 
        col = plan.expression.strip() if plan.expression else ""
        if not col or col not in df.columns:
            candidates = [c for c in df.columns if str(c).startswith("l2_")]
            if not candidates:
                # 任意数值列
                candidates = [
                    c
                    for c in df.columns
                    if c not in ("instrument_key", "trading_date", "symbol")
                    and pd.api.types.is_numeric_dtype(df[c])
                ]
            if not candidates:
                return FactorFrame.from_records([])
            col = candidates[0]

        ik_col = "instrument_key" if "instrument_key" in df.columns else None
        if ik_col is None and "symbol" in df.columns:
            df = df.copy()
            df["instrument_key"] = df["symbol"].map(self._to_instrument_key)
            ik_col = "instrument_key"

        records = []
        for _, row in df.iterrows():
            val = row[col]
            if pd.isna(val):
                continue
            td = row.get("trading_date")
            day = td.date().isoformat() if hasattr(td, "date") else str(td)[:10]
            records.append(
                {
                    "instrument_key": str(row[ik_col]),
                    "trading_date": day,
                    "factor_code": code,
                    "factor_version": version,
                    "value": float(val),
                }
            )
        return FactorFrame.from_records(records, layout="long")

    def _load_panel(self, plan: ComputePlan, query) -> pd.DataFrame | None:
        """尽力调用 enrich_panel；失败返回 None（测试应注入 l2_panel）。"""
        try:
            from app.services.level2_factor_panel import enrich_panel
        except Exception:
            return None
        meta = plan.metadata or {}
        instruments = list(meta.get("instruments") or [])
        if not instruments:
            return None
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
            return None
        try:
            return enrich_panel(market, directory=meta.get("l2_directory"))
        except Exception:
            return None

    @staticmethod
    def _to_instrument_key(symbol: object) -> str:
        text = str(symbol or "").upper()
        if text.endswith(".SH") or text.endswith(".SZ"):
            code = text.split(".")[0]
            return f"CNStock:{code}"
        if text.isdigit() and len(text) == 6:
            return f"CNStock:{text}"
        return f"CNStock:{text}"
