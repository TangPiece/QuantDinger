"""DataQuery：研究数据唯一读面（禁止实时行情 API）。"""

from __future__ import annotations

import io
from datetime import date, datetime, timezone
from typing import Optional, Sequence

import pandas as pd
import pyarrow.parquet as pq

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
    """从 Canonical Store + Registry 读取研究数据。

    构造时注入 store/registry；模块内不 import 行情 HTTP 客户端。
    """

    def __init__(self, store: CanonicalStore, registry: ResearchRegistry) -> None:
        self._store = store
        self._registry = registry

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
        """读取 Canonical 日线；Phase 1A 仅支持 price_policy.adjustment=none。"""
        del snapshot_id  # 绑定通过 store 内已发布文件体现
        if frequency != "1d":
            raise DataQueryError(f"unsupported frequency: {frequency}")
        policy = price_policy or PricePolicy()
        if policy.adjustment != "none":
            raise NotImplementedError(
                "Phase 1A only supports PricePolicy.adjustment='none' (raw Canonical prices)"
            )
        frames: list[pd.DataFrame] = []
        for year, month in _iter_months(start, end):
            prefix = market_daily_prefix(exchange=exchange, year=year, month=month)
            for key in self._store.list_keys(prefix):
                if not key.endswith(".parquet"):
                    continue
                df = self._read_parquet_df(key)
                frames.append(df)
        if not frames:
            return _empty_market()
        out = pd.concat(frames, ignore_index=True)
        out = _ensure_datetime_date(out, "trading_date")
        keys = set(instrument_keys)
        if keys:
            out = out[out["instrument_key"].isin(keys)]
        out = out[(out["trading_date"] >= start) & (out["trading_date"] <= end)]
        return out.reset_index(drop=True)

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
            for key in self._store.list_keys(prefix):
                if key.endswith(".parquet"):
                    frames.append(self._read_parquet_df(key))
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
        frames: list[pd.DataFrame] = []
        for key in self._store.list_keys(prefix):
            if key.endswith(".parquet"):
                frames.append(self._read_parquet_df(key))
        if not frames:
            return []
        out = pd.concat(frames, ignore_index=True)
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
        frames = [
            self._read_parquet_df(k)
            for k in self._store.list_keys(prefix)
            if k.endswith(".parquet")
        ]
        if not frames:
            return pd.DataFrame(
                columns=[
                    "instrument_key",
                    "trading_date",
                    "status",
                    "is_suspended",
                    "is_limit_up",
                    "is_limit_down",
                ]
            )
        out = pd.concat(frames, ignore_index=True)
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
        for year, _month in _iter_months(start, end):
            prefix = corporate_action_prefix(exchange=exchange, year=year)
            for key in self._store.list_keys(prefix):
                if key.endswith(".parquet"):
                    frames.append(self._read_parquet_df(key))
        if not frames:
            return pd.DataFrame(
                columns=["instrument_key", "effective_date", "action_type", "cash_dividend", "split_ratio"]
            )
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
                    "Phase 1A research path expects R2 factor assets (backend=r2_factor)"
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
        frames = [
            self._read_parquet_df(k)
            for k in self._store.list_keys(prefix)
            if k.endswith(".parquet")
        ]
        if not frames:
            return pd.DataFrame(
                columns=["instrument_key", "trading_date", "factor_code", "factor_version", "value"]
            )
        return pd.concat(frames, ignore_index=True)

    def _read_parquet_df(self, key: str) -> pd.DataFrame:
        data = self._store.get_bytes(key)
        table = pq.read_table(io.BytesIO(data))
        return table.to_pandas()


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
