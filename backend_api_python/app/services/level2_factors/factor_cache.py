"""图表补下来的 Level2 因子，按日写成 Parquet。

``{目录}/{YYYYMMDD}.parquet`` 里一行是一只股票。超过 ``LEVEL2_FACTOR_CACHE_MAX_MB``
（默认 512）或早于 ``LEVEL2_FACTOR_CACHE_MAX_DAYS``（默认 370）的交易日会被删掉。
设为 0 表示该项目不淘汰。测试可以换 ``MemoryFactorCache``，不写文件、不连数据库。
"""
from __future__ import annotations

import fcntl
import json
import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_log = logging.getLogger(__name__)
_TABLE = "qd_level2_factor_cache"
_MB = 1024 ** 2
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_table_dropped = False


def factor_limit_bytes() -> int | None:
    """临时表容量。未设置时 512MB，小于等于 0 不按容量删。"""
    return _limit(os.getenv("LEVEL2_FACTOR_CACHE_MAX_MB", ""), default=512.0, unit=_MB)


def factor_max_days() -> int | None:
    """临时表保留天数。未设置时 370，覆盖近一年；小于等于 0 不过期。"""
    return _days(os.getenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", ""), default=370)


def cutoff_date(max_days: int | None, *, today: datetime | None = None) -> str | None:
    """上海日期往前 ``max_days`` 天，得到 YYYYMMDD。早于这个值的交易日过期。"""
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
    """测试用的内存临时表。接口和数据库实现一致。"""

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


class ParquetFactorStore:
    """``data/level2_factors/{YYYYMMDD}.parquet``。同一天其他股票的行会保留。"""

    def __init__(self, directory: Path | None = None) -> None:
        from app.services.level2_factor_panel import default_factor_directory

        self.directory = Path(directory) if directory is not None else default_factor_directory()
        self.directory.mkdir(parents=True, exist_ok=True)

    def has(self, symbol: str, date: str) -> bool:
        """这一天的文件里已经有这只股票。文件不在本地时先试 R2。"""
        frame = _load_day(self.directory, str(date))
        return _symbol_present(frame, symbol)

    def upsert(self, symbol: str, date: str, factors: dict[str, Any]) -> None:
        """替换该日文件中这一只股票的行，再上传 R2 并按容量和保留天数收口。"""
        day = str(date)
        code = str(symbol).upper()
        ready = _json_ready(factors)
        lock_path = self.directory / f".{day}.write.lock"
        with lock_path.open("a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                _replace_symbol_row(self.directory, code, day, ready)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        publish_factor_file(self.directory / f"{day}.parquet", keep_date=day)

    def history(self, symbol: str, before: str, limit: int) -> list[dict[str, Any]]:
        """更早的因子行，先读本地，缺的日期再从 R2 拉回本地。"""
        code = str(symbol).upper()
        chosen = _history_dates(self.directory, code, str(before), int(limit))
        output = []
        for date in chosen:
            frame = _load_day(self.directory, date)
            row = _symbol_row(frame, code)
            if row is None:
                continue
            output.append({"trade_date": date, "symbol": code, **row})
        return output

    def fetch(self, symbol: str, dates: list[str]) -> dict[str, dict[str, Any]]:
        """读出这只股票在给定交易日上的因子。没有的日期不出现。"""
        code = str(symbol).upper()
        found: dict[str, dict[str, Any]] = {}
        for date in sorted({str(item) for item in dates if str(item)}):
            row = _symbol_row(_load_day(self.directory, date), code)
            if row is not None:
                found[date] = row
        return found

    def enforce(self, keep_date: str) -> None:
        """删掉过期或超出容量的日期文件。``keep_date`` 正在写入，不删。"""
        from app.services.level2_factor_panel import clear_panel_cache

        days = _factor_files(self.directory)
        sizes = {path.stem: path.stat().st_size for path in days}
        victims = dates_to_evict(
            list(sizes),
            sizes,
            cutoff=cutoff_date(factor_max_days()),
            limit=factor_limit_bytes(),
            keep=str(keep_date),
        )
        for date in victims:
            if date == str(keep_date):
                continue
            path = self.directory / f"{date}.parquet"
            if path.is_file():
                path.unlink()
        if victims:
            clear_panel_cache()


def publish_factor_file(path: Path, *, keep_date: str | None = None) -> None:
    """把已经写好的日频文件上传到 R2，并按本地上限收口。"""
    path = Path(path)
    if not path.is_file():
        return
    from .r2_factors import upload_factor_file

    upload_factor_file(path.stem, path.read_bytes())
    ParquetFactorStore(path.parent).enforce(keep_date=keep_date or path.stem)


def get_factor_cache() -> ParquetFactorStore:
    """图表和后台补数用的日频 Parquet。顺手删掉不再使用的数据库临时表。"""
    _drop_factor_table()
    return ParquetFactorStore()


def _drop_factor_table() -> None:
    """只尝试一次。数据库不可用时忽略，因子仍写在本地 Parquet。"""
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


def _replace_symbol_row(directory: Path, symbol: str, date: str, factors: dict[str, Any]) -> None:
    """重写当天文件，只换这一只股票，并丢掉已落盘的滚动列。"""
    import pandas as pd

    from app.services.level2_factor_panel import clear_panel_cache

    from .names import stored_columns

    clear_panel_cache()
    path = directory / f"{date}.parquet"
    columns = stored_columns()
    current = pd.read_parquet(path) if path.is_file() else pd.DataFrame(columns=columns)
    if not current.empty and "symbol" in current.columns:
        kept = current.loc[current["symbol"].astype(str).str.upper() != symbol]
    else:
        kept = current.iloc[0:0]
    row = {"trade_date": date, "symbol": symbol}
    row.update({column: factors.get(column, float("nan")) for column in columns if column not in row})
    merged = pd.concat([kept, pd.DataFrame([row])], ignore_index=True)
    for column in columns:
        if column not in merged.columns:
            merged[column] = float("nan")
    merged = merged[columns]
    temporary = directory / f".{date}.parquet.tmp"
    merged.to_parquet(temporary, index=False)
    temporary.replace(path)
    clear_panel_cache()


def _load_day(directory: Path, date: str):
    from app.services.level2_factor_panel import _read_day

    return _read_day(directory, date)


def _symbol_present(frame, symbol: str) -> bool:
    return _symbol_row(frame, symbol) is not None


def _symbol_row(frame, symbol: str) -> dict[str, Any] | None:
    if frame is None or getattr(frame, "empty", True) or "symbol" not in frame.columns:
        return None
    code = str(symbol).upper()
    matched = frame.loc[frame["symbol"].astype(str).str.upper() == code]
    if matched.empty:
        return None
    record = matched.iloc[-1]
    return {
        str(column): record[column]
        for column in matched.columns
        if str(column) not in {"trade_date", "symbol"}
    }


def _history_dates(directory: Path, symbol: str, before: str, limit: int) -> list[str]:
    """本地已有的更早日期优先。数量不够时，把 R2 上缺的日期拉下来再选。"""
    local = [path.stem for path in _factor_files(directory) if path.stem < before]
    if len(local) >= limit:
        return local[-limit:]
    _pull_missing_history(directory, local, before, limit)
    refreshed = [path.stem for path in _factor_files(directory) if path.stem < before]
    return refreshed[-limit:]


def _pull_missing_history(directory: Path, local: list[str], before: str, limit: int) -> None:
    """本地更早的日子不够滚动窗口时，从 R2 把缺的日期拉回本地。"""
    from .r2_factors import download_factor_file, list_factor_dates

    have = {date for date in local if date < before}
    if len(have) >= limit:
        return
    remote = [date for date in list_factor_dates() if date < before and date not in have]
    for date in reversed(remote):
        if len(have) >= limit:
            break
        payload = download_factor_file(date)
        if not payload:
            continue
        path = directory / f"{date}.parquet"
        temporary = path.with_suffix(".parquet.part")
        temporary.write_bytes(payload)
        temporary.replace(path)
        have.add(date)


def _factor_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.glob("*.parquet")
        if path.stem.isdigit() and len(path.stem) == 8
    )


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
