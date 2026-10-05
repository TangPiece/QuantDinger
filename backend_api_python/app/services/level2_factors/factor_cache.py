"""图表补数用的 Level2 因子缓存：读写都走 D1（经 Worker）。

``MemoryFactorCache`` 仍供单测注入，不连网。
本地日 parquet 不再作为生产缓存。
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_log = logging.getLogger(__name__)
_TABLE = "qd_level2_factor_cache"
_MB = 1024 ** 2
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_table_dropped = False


def factor_limit_bytes() -> int | None:
    """本地 SQLite 读缓存体积上限（字节）。默认 2048MB，约单股三年 + 多标的余量。"""
    return _limit(os.getenv("LEVEL2_FACTOR_CACHE_MAX_MB", ""), default=2048.0, unit=_MB)


def factor_max_days() -> int | None:
    """本地 SQLite 读缓存保留天数。默认 1200（约三年日历日）。"""
    return _days(os.getenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", ""), default=1200)


def cutoff_date(max_days: int | None, *, today: datetime | None = None) -> str | None:
    """上海日期往前 ``max_days`` 天，得到 YYYYMMDD。"""
    if max_days is None or max_days <= 0:
        return None
    current = today or datetime.now(_SHANGHAI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_SHANGHAI)
    day = current.astimezone(_SHANGHAI).date() - timedelta(days=max_days)
    return day.strftime("%Y%m%d")


def dates_to_evict(
    dates: list[str],
    sizes: dict[str, int],
    *,
    cutoff: str | None,
    limit: int | None,
    keep: str,
) -> list[str]:
    """先去掉过期交易日，再按容量从最老的日期删。``keep`` 是正在写入的那一天。"""
    victims: list[str] = []
    remaining = sorted({str(item) for item in dates})
    if cutoff:
        expired = [day for day in remaining if day < cutoff and day != str(keep)]
        victims.extend(expired)
        remaining = [day for day in remaining if day not in expired]
    if limit is None:
        return victims
    total = sum(int(sizes.get(day, 0)) for day in remaining)
    for day in remaining:
        if total <= limit:
            break
        if day == str(keep):
            continue
        victims.append(day)
        total -= int(sizes.get(day, 0))
    return victims


class MemoryFactorCache:
    """测试用的内存临时表。接口和 D1 实现一致。"""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}

    def has(self, symbol: str, date: str) -> bool:
        return (symbol, str(date)) in self.rows

    def upsert(self, symbol: str, date: str, factors: dict[str, Any]) -> None:
        self.rows[(symbol, str(date))] = _json_ready(factors)
        self.enforce(keep_date=str(date))

    def history(self, symbol: str, before: str, limit: int) -> list[dict[str, Any]]:
        chosen = sorted(date for code, date in self.rows if code == symbol and date < str(before))
        return [
            {"trade_date": date, "symbol": symbol, **self.rows[(symbol, date)]}
            for date in chosen[-limit:]
        ]

    def fetch(self, symbol: str, dates: list[str]) -> dict[str, dict[str, Any]]:
        wanted = {str(item) for item in dates}
        return {
            date: dict(factors)
            for (code, date), factors in self.rows.items()
            if code == symbol and date in wanted
        }

    def enforce(self, keep_date: str) -> None:
        grouped: dict[str, int] = {}
        for (_code, date), factors in self.rows.items():
            grouped[date] = grouped.get(date, 0) + len(json.dumps(factors, ensure_ascii=False).encode("utf-8"))
        victims = set(dates_to_evict(
            list(grouped),
            grouped,
            cutoff=cutoff_date(factor_max_days()),
            limit=factor_limit_bytes(),
            keep=str(keep_date),
        ))
        if not victims:
            return
        self.rows = {key: value for key, value in self.rows.items() if key[1] not in victims}


class D1FactorStore:
    """生产缓存：读写都经 Worker 访问 D1 ``l2_factors``。"""

    def has(self, symbol: str, date: str) -> bool:
        from . import d1_client, d1_factors

        if not d1_client.configured():
            return False
        code = str(symbol).upper()
        day = str(date)
        rows = d1_factors.fetch_symbols([code], [day])
        return any(str(row.get("symbol", "")).upper() == code for row in rows)

    def upsert(self, symbol: str, date: str, factors: dict[str, Any]) -> None:
        """单行写入 D1；未配置 Worker 时只打日志。"""
        from . import d1_client, d1_factors
        from .names import stored_columns

        if not d1_client.configured():
            _log.warning("D1 Worker 未配置，跳过因子 upsert %s %s", symbol, date)
            return
        ready = _json_ready(factors)
        row = {"trade_date": str(date), "symbol": str(symbol).upper()}
        for column in stored_columns():
            if column in {"trade_date", "symbol"}:
                continue
            row[column] = ready.get(column)
        d1_factors.upsert_rows([row])
        from app.services.level2_factor_panel import clear_panel_cache
        from . import local_d1_cache

        # 写 D1 后丢掉本地该行，下次读会重新回填，避免脏缓存。
        local_d1_cache.invalidate([str(symbol).upper()], [str(date)])
        clear_panel_cache()

    def history(self, symbol: str, before: str, limit: int) -> list[dict[str, Any]]:
        from . import d1_client, d1_factors

        if not d1_client.configured():
            return []
        return d1_factors.fetch_symbol_history(str(symbol).upper(), str(before), int(limit))

    def fetch(self, symbol: str, dates: list[str]) -> dict[str, dict[str, Any]]:
        from . import d1_client, d1_factors

        code = str(symbol).upper()
        wanted = sorted({str(item) for item in dates if str(item)})
        found: dict[str, dict[str, Any]] = {}
        if not d1_client.configured() or not wanted:
            return found
        for row in d1_factors.fetch_symbols([code], wanted):
            day = str(row.get("trade_date") or "")
            if day:
                found[day] = {
                    key: value
                    for key, value in row.items()
                    if key not in {"trade_date", "symbol"}
                }
        return found

    def enforce(self, keep_date: str) -> None:
        """D1 不在本地淘汰。"""
        del keep_date


# 旧名兼容：图表补数与测试里可能仍引用 ParquetFactorStore。
ParquetFactorStore = D1FactorStore


def publish_factor_file(path, *, keep_date: str | None = None) -> None:
    """把已经写好的日频文件写入 D1；成功后删除本地日文件。"""
    from pathlib import Path

    path = Path(path)
    if not path.is_file():
        return
    from . import d1_client, d1_factors

    if d1_client.configured():
        try:
            d1_factors.upsert_day(path.stem, path)
            path.unlink(missing_ok=True)
            from . import local_d1_cache

            local_d1_cache.invalidate(dates=[path.stem])
            from app.services.level2_factor_panel import clear_panel_cache

            clear_panel_cache()
        except Exception:
            _log.warning("Level2 因子写入 D1 失败 %s", path.stem, exc_info=True)
    else:
        _log.warning("D1 Worker 未配置，跳过因子发布 %s", path.stem)
    del keep_date


def get_factor_cache() -> D1FactorStore:
    """图表和后台补数用的 D1 存储。顺手删掉不再使用的数据库临时表。"""
    _drop_factor_table()
    return D1FactorStore()


def _drop_factor_table() -> None:
    """只尝试一次。数据库不可用时忽略。"""
    global _table_dropped
    if _table_dropped:
        return
    _table_dropped = True
    try:
        from app.utils.db import get_db_connection

        with get_db_connection() as db:
            cursor = db.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS {_TABLE}")
            db.commit()
    except Exception:
        _log.warning("删除 Level2 因子临时表失败", exc_info=True)


def _json_ready(factors: dict[str, Any]) -> dict[str, Any]:
    """NaN 写成 null，避免 JSON 非法。"""
    ready: dict[str, Any] = {}
    for key, value in factors.items():
        if hasattr(value, "item") and not isinstance(value, (str, bytes)):
            try:
                value = value.item()
            except Exception:
                pass
        if isinstance(value, float) and not math.isfinite(value):
            ready[str(key)] = None
        else:
            ready[str(key)] = value
    return ready


def _limit(raw: str, *, default: float, unit: int) -> int | None:
    text = str(raw or "").strip()
    if not text:
        amount = default
    else:
        try:
            amount = float(text)
        except ValueError:
            amount = default
    if amount <= 0:
        return None
    return int(amount * unit)


def _days(raw: str, *, default: int) -> int | None:
    text = str(raw or "").strip()
    if not text:
        amount = default
    else:
        try:
            amount = int(float(text))
        except ValueError:
            amount = default
    return amount if amount > 0 else None
