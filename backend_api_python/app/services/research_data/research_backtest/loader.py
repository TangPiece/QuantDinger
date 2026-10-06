"""加载 5A TargetPosition 与价格面板。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.canonical_store import CanonicalStore


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not hasattr(v, "hour"):
        return v
    return date.fromisoformat(str(v)[:10])


def load_targets_by_date(
    store: CanonicalStore | None,
    strategy_hash: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[date, list[dict[str, Any]]]:
    """按信号日分组目标权重；支持注入或读 ``qd/strategy/{hash}/target_positions/``。"""
    meta = dict(metadata or {})
    if meta.get("targets_by_date") is not None:
        raw = meta["targets_by_date"]
        out: dict[date, list[dict[str, Any]]] = {}
        if isinstance(raw, Mapping):
            for k, rows in raw.items():
                d = _as_date(k)
                out[d] = [dict(r) for r in rows]
        return out
    if meta.get("target_positions") is not None:
        return _group_rows(list(meta["target_positions"]))
    if store is None:
        raise ValueError("store required when targets not injected")
    from app.services.research_data import config as rd_config

    prefix = (
        f"{rd_config.canonical_prefix()}/strategy/{strategy_hash}/target_positions"
    )
    df = CanonicalRepository(store).read_parquet_df(prefix=prefix)
    if df is None or df.empty:
        return {}
    return _group_rows(df.to_dict(orient="records"))


def _group_rows(rows: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    out: dict[date, list[dict[str, Any]]] = {}
    for r in rows:
        d = _as_date(r["trading_date"])
        out.setdefault(d, []).append(dict(r))
    return out


def load_price_bars(
    store: CanonicalStore | None,
    *,
    instruments: set[str],
    start: date,
    end: date,
    exchange: str = "CN",
    metadata: Mapping[str, Any] | None = None,
) -> dict[tuple[str, date], dict[str, float]]:
    """加载 ``(instrument, date) → {open, close, ...}``；测试可注入 ``price_bars``。"""
    meta = dict(metadata or {})
    if meta.get("price_bars") is not None:
        return index_price_bars(meta["price_bars"])
    if store is None:
        raise ValueError("store required when price_bars not injected")
    # Canonical market daily：按年/月分区扫读后过滤
    from app.services.research_data import config as rd_config

    prefix = f"{rd_config.canonical_prefix()}/canonical/market/daily/exchange={exchange}"
    try:
        df = CanonicalRepository(store).read_parquet_df(prefix=prefix)
    except Exception as exc:
        raise RuntimeError(f"failed to load market daily for {exchange}") from exc
    if df is None or df.empty:
        return {}
    indexed: dict[tuple[str, date], dict[str, float]] = {}
    for row in df.to_dict(orient="records"):
        key = str(row.get("instrument_key") or "")
        if instruments and key not in instruments:
            continue
        d = _as_date(row["trading_date"])
        if d < start or d > end:
            continue
        indexed[(key, d)] = {
            "open": float(row["open"]) if row.get("open") is not None else float("nan"),
            "close": float(row["close"])
            if row.get("close") is not None
            else float("nan"),
            "high": float(row["high"]) if row.get("high") is not None else float("nan"),
            "low": float(row["low"]) if row.get("low") is not None else float("nan"),
        }
    return indexed


def index_price_bars(
    bars: Any,
) -> dict[tuple[str, date], dict[str, float]]:
    """将 list/dict 价格行规范为索引。"""
    if isinstance(bars, Mapping) and bars:
        first_key = next(iter(bars.keys()))
        if isinstance(first_key, tuple) and len(first_key) == 2:
            out: dict[tuple[str, date], dict[str, float]] = {}
            for (inst, d), bar in bars.items():
                dd = _as_date(d)
                out[(str(inst), dd)] = {
                    "open": float(bar.get("open", float("nan"))),
                    "close": float(bar.get("close", float("nan"))),
                    "high": float(bar.get("high", float("nan"))),
                    "low": float(bar.get("low", float("nan"))),
                }
            return out
    indexed: dict[tuple[str, date], dict[str, float]] = {}
    for row in bars:
        key = str(row["instrument_key"])
        d = _as_date(row["trading_date"])
        indexed[(key, d)] = {
            "open": float(row["open"]) if row.get("open") is not None else float("nan"),
            "close": float(row["close"])
            if row.get("close") is not None
            else float("nan"),
            "high": float(row["high"]) if row.get("high") is not None else float("nan"),
            "low": float(row["low"]) if row.get("low") is not None else float("nan"),
        }
    return indexed
