"""DataQuery：研究数据唯一读面（禁止实时行情 API）。

读路径：DataQuery → CanonicalRepository → (Local/R2 Store + DuckDB scan)。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Sequence

import pandas as pd

from .canonical_repository import CanonicalRepository
from .canonical_store import CanonicalStore
from .contracts import DatasetHandle, PricePolicy
from .paths import (
    corporate_action_prefix,
    market_daily_prefix,
    pit_fundamental_prefix,
    trading_status_prefix,
    universe_snapshot_prefix,
)
from .registry import ResearchRegistry


class DataQueryError(RuntimeError):
    """研究查询失败。"""


class DataQuery:
    """从 CanonicalRepository + Registry 读取研究数据。

    构造时注入 store/registry；模块内不 import 行情 HTTP 客户端。
    """

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        repository: CanonicalRepository | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        # 允许测试注入自定义 Repository；默认由 store 构建
        self._repo = repository or CanonicalRepository(store)

    @property
    def repository(self) -> CanonicalRepository:
        return self._repo

    def market(
        self,
        instrument_keys: Sequence[str],
        start: date,
        end: date,
        frequency: str = "1d",
        *,
        price_policy: PricePolicy | None = None,
        exchange: str = "CN",
        snapshot_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取 Canonical 日线；none=raw，post=后复权，pre 仍未实现。"""
        del snapshot_id  # 绑定通过 store 内已发布文件体现
        if frequency != "1d":
            raise DataQueryError(f"unsupported frequency: {frequency}")
        policy = price_policy or PricePolicy()
        if policy.adjustment == "pre":
            raise NotImplementedError(
                "PricePolicy.adjustment='pre' is not implemented in Phase 1B"
            )
        if policy.adjustment not in ("none", "post"):
            raise DataQueryError(f"unsupported adjustment: {policy.adjustment}")

        frames: list[pd.DataFrame] = []
        for year, month in _iter_months(start, end):
            prefix = market_daily_prefix(exchange=exchange, year=year, month=month)
            df = self._repo.read_parquet_df(
                prefix=prefix,
                order_by=("instrument_key", "trading_date"),
            )
            if not df.empty:
                frames.append(df)
        if not frames:
            return _empty_market()
        out = pd.concat(frames, ignore_index=True)
        out = _ensure_datetime_date(out, "trading_date")
        keys = set(instrument_keys)
        if keys:
            out = out[out["instrument_key"].isin(keys)]
        out = out[(out["trading_date"] >= start) & (out["trading_date"] <= end)]
        out = out.reset_index(drop=True)
        if policy.adjustment == "post":
            out = self._apply_post_adjustment(out, exchange=exchange, start=start, end=end)
        return out

    def fundamental(
        self,
        instrument_keys: Sequence[str],
        metrics: Sequence[str],
        knowledge_time: datetime,
        *,
        exchange: str = "CN",
        snapshot_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """PIT：available_time <= knowledge_time，再按 available_time/revision 取最新。"""
        del snapshot_id
        kt = _as_utc(knowledge_time)
        frames: list[pd.DataFrame] = []
        # 覆盖常见年份窗口：knowledge_time 年与前后一年
        years = {kt.year - 1, kt.year, kt.year + 1}
        for year in sorted(years):
            prefix = pit_fundamental_prefix(exchange=exchange, year=year)
            df = self._repo.read_parquet_df(prefix=prefix)
            if not df.empty:
                frames.append(df)
        if not frames:
            return _empty_pit()
        out = pd.concat(frames, ignore_index=True)
        if "available_time" not in out.columns:
            raise DataQueryError("pit table missing available_time")
        out["available_time"] = pd.to_datetime(out["available_time"], utc=True)
        keys = set(instrument_keys)
        mets = set(metrics)
        if keys:
            out = out[out["instrument_key"].isin(keys)]
        if mets:
            out = out[out["metric_code"].isin(mets)]
        # Leakage 硬过滤
        out = out[out["available_time"] <= kt]
        if out.empty:
            return out.reset_index(drop=True)
        out["revision"] = out.get("revision", 0).fillna(0).astype(int)
        out = out.sort_values(
            ["instrument_key", "metric_code", "available_time", "revision"],
            ascending=[True, True, False, False],
        )
        out = out.drop_duplicates(subset=["instrument_key", "metric_code"], keep="first")
        return out.reset_index(drop=True)

    def universe(
        self,
        universe_code: str,
        knowledge_time: datetime,
        *,
        snapshot_id: Optional[str] = None,
        universe_version: Optional[str] = None,
    ) -> list[str]:
        """仅读 Canonical universe snapshot；禁止查 PG。"""
        as_of = knowledge_time.date() if isinstance(knowledge_time, datetime) else knowledge_time
        version = universe_version
        if version is None and snapshot_id:
            # 从 snapshot items 推断 universe 路径版本
            snap = self._registry.get_snapshot(snapshot_id)
            for item in snap.items:
                uri = item.r2_uri or ""
                marker = f"code={universe_code}/version="
                if marker in uri:
                    version = uri.split(marker, 1)[1].split("/", 1)[0]
                    break
        if not version:
            raise DataQueryError(
                "universe() requires universe_version or snapshot_id that pins a universe snapshot"
            )
        prefix = universe_snapshot_prefix(universe_code=universe_code, universe_version=version)
        out = self._repo.read_parquet_df(prefix=prefix)
        if out.empty:
            return []
        valid_from = pd.to_datetime(out["valid_from"], errors="coerce")
        as_of_ts = pd.Timestamp(as_of)
        if "valid_to" in out.columns:
            valid_to = pd.to_datetime(out["valid_to"], errors="coerce")
            # 空 valid_to = 开放区间
            mask_open = valid_to.isna() | (valid_to >= as_of_ts)
        else:
            mask_open = True
        mask = (valid_from <= as_of_ts) & mask_open
        if snapshot_id and "snapshot_id" in out.columns:
            mask = mask & (out["snapshot_id"] == snapshot_id)
        members = out.loc[mask, "instrument_key"].astype(str).tolist()
        return sorted(set(members))

    def trading_status(
        self,
        instrument_keys: Sequence[str],
        trading_date: date,
        *,
        exchange: str = "CN",
        snapshot_id: Optional[str] = None,
    ) -> pd.DataFrame:
        del snapshot_id
        prefix = trading_status_prefix(
            exchange=exchange, year=trading_date.year, month=trading_date.month
        )
        out = self._repo.read_parquet_df(prefix=prefix)
        empty_cols = [
            "instrument_key",
            "trading_date",
            "status",
            "is_suspended",
            "is_limit_up",
            "is_limit_down",
        ]
        if out.empty:
            return pd.DataFrame(columns=empty_cols)
        out = _ensure_datetime_date(out, "trading_date")
        keys = set(instrument_keys)
        if keys:
            out = out[out["instrument_key"].isin(keys)]
        out = out[out["trading_date"] == trading_date]
        return out.reset_index(drop=True)

    def corporate_actions(
        self,
        instrument_keys: Sequence[str],
        start: date,
        end: date,
        *,
        exchange: str = "CN",
        snapshot_id: Optional[str] = None,
    ) -> pd.DataFrame:
        del snapshot_id
        frames: list[pd.DataFrame] = []
        years = {start.year, end.year}
        for year in sorted(years):
            prefix = corporate_action_prefix(exchange=exchange, year=year)
            df = self._repo.read_parquet_df(prefix=prefix)
            if not df.empty:
                frames.append(df)
        empty_cols = [
            "instrument_key",
            "effective_date",
            "action_type",
            "cash_dividend",
            "split_ratio",
        ]
        if not frames:
            return pd.DataFrame(columns=empty_cols)
        out = pd.concat(frames, ignore_index=True)
        out = _ensure_datetime_date(out, "effective_date")
        keys = set(instrument_keys)
        if keys:
            out = out[out["instrument_key"].isin(keys)]
        out = out[(out["effective_date"] >= start) & (out["effective_date"] <= end)]
        return out.reset_index(drop=True)

    def dataset(self, dataset_ref: str) -> DatasetHandle:
        return self._registry.get_dataset(dataset_ref)

    def feature(
        self,
        feature_refs: Sequence[str],
        *,
        dataset_ref: str,
        knowledge_time: datetime,
        exchange: str = "CN",
    ) -> pd.DataFrame:
        """按 Registry backend 读取因子；d1_l2_factors 未实现热路径时显式报错。"""
        del knowledge_time  # 日频因子按交易日面板；PIT 类应走 fundamental
        handle = self.dataset(dataset_ref)
        frames: list[pd.DataFrame] = []
        for ref in feature_refs:
            feat = self._registry.get_feature(ref)
            if feat.backend == "d1_l2_factors":
                raise DataQueryError(
                    "feature backend=d1_l2_factors is a hot store; "
                    "Phase 1 research path expects R2 factor assets (backend=r2_factor)"
                )
            if feat.backend == "r2_factor":
                factor_set = feat.definition.get("factor_set") or f"{feat.code}@{feat.version}"
                frames.append(self._load_factor_set(factor_set, exchange=exchange))
            elif feat.backend == "computed":
                # 最小：把 market 源列映射为因子值（完整 DSL 编译留给后续）
                col = feat.definition.get("source_column") or "close"
                market_df = self.market(
                    [],
                    date(1970, 1, 1),
                    date(2100, 1, 1),
                    price_policy=handle.definition.price_policy,
                    exchange=exchange,
                )
                if market_df.empty or col not in market_df.columns:
                    continue
                part = market_df[["instrument_key", "trading_date", col]].copy()
                part = part.rename(columns={col: "value"})
                part["factor_code"] = feat.code
                part["factor_version"] = feat.version
                frames.append(part)
            else:
                raise DataQueryError(f"unknown feature backend: {feat.backend}")
        if not frames:
            return pd.DataFrame(
                columns=["instrument_key", "trading_date", "factor_code", "factor_version", "value"]
            )
        out = pd.concat(frames, ignore_index=True)
        codes = {self._registry.get_feature(r).code for r in feature_refs}
        if "factor_code" in out.columns:
            out = out[out["factor_code"].isin(codes)]
        return out.reset_index(drop=True)

    def _load_factor_set(self, factor_set: str, *, exchange: str) -> pd.DataFrame:
        del exchange
        from . import config as rd_config

        prefix = f"{rd_config.canonical_prefix()}/factor/daily/factor_set={factor_set}"
        out = self._repo.read_parquet_df(prefix=prefix)
        if out.empty:
            return pd.DataFrame(
                columns=["instrument_key", "trading_date", "factor_code", "factor_version", "value"]
            )
        return out

    def _apply_post_adjustment(
        self,
        market: pd.DataFrame,
        *,
        exchange: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """用 Canonical corporate_action.split_ratio 做最小后复权。

        因子定义：对交易日 t，post_factor = ∏ split_ratio(effective_date > t)。
        无任何 CA 时显式报错（避免 silently 恒等导致 none==post）。
        """
        if market.empty:
            return market
        instruments = market["instrument_key"].astype(str).unique().tolist()
        # 取更宽 CA 窗口，覆盖 end 之后的拆分（后复权需要未来事件）
        ca_start = date(min(start.year, end.year) - 1, 1, 1)
        ca_end = date(end.year + 1, 12, 31)
        frames: list[pd.DataFrame] = []
        for year in range(ca_start.year, ca_end.year + 1):
            prefix = corporate_action_prefix(exchange=exchange, year=year)
            df = self._repo.read_parquet_df(prefix=prefix)
            if not df.empty:
                frames.append(df)
        if not frames:
            raise DataQueryError(
                "PricePolicy.adjustment='post' requires corporate_action in Canonical; none found"
            )
        ca = pd.concat(frames, ignore_index=True)
        ca = _ensure_datetime_date(ca, "effective_date")
        ca = ca[ca["instrument_key"].isin(instruments)]
        if ca.empty:
            raise DataQueryError(
                "PricePolicy.adjustment='post' found no corporate_action for requested instruments"
            )
        # split_ratio 缺省视为 1.0（无价格缩放）
        ca = ca.copy()
        ca["split_ratio"] = pd.to_numeric(ca["split_ratio"], errors="coerce").fillna(1.0)
        ca = ca.sort_values(["instrument_key", "effective_date"])

        out = market.copy()
        price_cols = [c for c in ("open", "high", "low", "close", "vwap") if c in out.columns]
        factors: list[float] = []
        for _, row in out.iterrows():
            ik = str(row["instrument_key"])
            td = row["trading_date"]
            subsequent = ca[(ca["instrument_key"] == ik) & (ca["effective_date"] > td)]
            factor = float(subsequent["split_ratio"].prod()) if len(subsequent) else 1.0
            factors.append(factor)
        out["_post_factor"] = factors
        for col in price_cols:
            out[col] = out[col].astype(float) * out["_post_factor"]
        # 拆分后成交量按因子反向缩放（金额不变）
        if "volume" in out.columns:
            out["volume"] = out["volume"].astype(float) / out["_post_factor"].replace(0, 1.0)
        out = out.drop(columns=["_post_factor"])
        return out.reset_index(drop=True)


def _iter_months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ensure_datetime_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col not in df.columns:
        return df
    out = df.copy()
    out[col] = pd.to_datetime(out[col]).dt.date
    return out


def _empty_market() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "instrument_key",
            "trading_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "vwap",
            "data_version",
        ]
    )


def _empty_pit() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "instrument_key",
            "metric_code",
            "available_time",
            "value",
            "revision",
            "publish_time",
        ]
    )
