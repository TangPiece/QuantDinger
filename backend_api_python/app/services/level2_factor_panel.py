"""把 Level2 日频因子按交易日并到 A 股日线上。

生产读侧以 Cloudflare D1（经 Worker）为真源，并带本地 SQLite 临时缓存。
``directory=`` 仅供单测注入本地日文件；未传时忽略日 parquet 目录。
5/10/20 日滚动列在拼好基础序列后现算。
因子在当日收盘后可知，对齐到该交易日的日 K，供次日开盘成交的研究口径使用。
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import pandas as pd

_log = logging.getLogger(__name__)

_CACHE: dict[tuple[str, str], pd.DataFrame | None] = {}
_CN_SUFFIX = (".SH", ".SZ", ".BJ")
# 最长滚动窗口是 20 日且含当日，前面最多再要 19 个已有交易日。
_WARMUP_DAYS = 19


def default_factor_directory() -> Path:
    """批量断点标记等遗留目录；不再作为读侧真源。"""
    root = Path(__file__).resolve().parents[2] / "data" / "level2_factor_markers"
    root.mkdir(parents=True, exist_ok=True)
    return root


def panel_directory() -> Path:
    """写侧/迁移用的本地目录。环境变量为空时用 ``level2_factor_markers``。"""
    raw = os.getenv("LEVEL2_FACTOR_PANEL_DIR", "").strip()
    path = Path(raw) if raw else default_factor_directory()
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_panel_cache() -> None:
    """清掉进程内日文件缓存；本地 SQLite 由调用方按需 invalidate。"""
    _CACHE.clear()


def canonical_symbol(value: object) -> str:
    """把 ``CNStock:600519`` / ``600519.XSHG`` / ``SH600519`` 收成 ``600519.SH``。"""
    raw = str(value or "").strip().upper()
    if ":" in raw:
        raw = raw.split(":")[-1]
    raw = raw.split("@")[0]
    replacements = {".XSHG": ".SH", ".XSHE": ".SZ", ".XBJS": ".BJ"}
    for suffix, target in replacements.items():
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)] + target
    # 图表和腾讯行情使用 SH/SZ/BJ 前缀。不转成后缀时，面板会把整只股票跳过。
    prefixed = re.fullmatch(r"(SH|SZ|BJ)(\d{6})", raw)
    if prefixed:
        return f"{prefixed.group(2)}.{prefixed.group(1)}"
    if re.fullmatch(r"\d{6}", raw):
        if raw[0] in "69":
            raw += ".SH"
        elif raw[0] in "03":
            raw += ".SZ"
        else:
            raw += ".BJ"
    return raw


def session_dates(index: pd.Index) -> pd.DatetimeIndex:
    """日 K 的时间戳按 UTC 理解，再换到上海交易日。

    腾讯日线日期会按机器本地午夜转成 unix。上海时区能把前一晚的 UTC
    还原成当日交易日，避免和因子表里的 ``YYYYMMDD`` 错一天。
    """
    stamps = pd.to_datetime(index, errors="coerce", utc=True)
    local = pd.DatetimeIndex(stamps).tz_convert("Asia/Shanghai").tz_localize(None)
    return local.normalize()


def enrich_panel(
    frames: dict[str, pd.DataFrame],
    members: list[dict] | None = None,
    *,
    directory: Path | str | None = None,
) -> dict[str, pd.DataFrame]:
    """给 CNStock 日线加上 ``l2_*`` 列。其它市场保持原表。

    未传 ``directory`` 时读 D1（经本地 SQLite 缓存）；显式传入目录时供单测读本地日文件。
    """
    from app.services.level2_factors import d1_client

    identities = _identities(members or [])
    selected: list[tuple[str, str, pd.DataFrame]] = []
    for key, frame in frames.items():
        market, symbol = identities.get(key, ("", canonical_symbol(key)))
        if not _is_china_stock(market, symbol) or frame is None or frame.empty:
            continue
        selected.append((key, symbol, frame))
    if not selected:
        return dict(frames)

    needed: set[str] = set()
    sessions: dict[str, pd.DatetimeIndex] = {}
    for key, _symbol, frame in selected:
        session = session_dates(frame.index)
        sessions[key] = session
        needed.update(stamp.strftime("%Y%m%d") for stamp in session if not pd.isna(stamp))
    symbols = sorted({symbol for _key, symbol, _frame in selected})

    # 单测可注入日 parquet 目录；生产走 D1 + 本地 SQLite。
    if directory is not None:
        path = Path(directory)
        if len(symbols) == 1:
            table = _load_symbol_base_local(path, symbols[0], sorted(needed))
        else:
            table = _load_cross_section_local(path, symbols, sorted(needed))
    elif not d1_client.configured():
        return dict(frames)
    elif len(symbols) == 1:
        table = _load_symbol_base_d1(symbols[0], sorted(needed))
    else:
        table = _load_cross_section_d1(symbols, sorted(needed))

    output = dict(frames)
    if table.empty:
        return output
    table = _with_rollups(table)
    factor_columns = [column for column in table.columns if str(column).startswith("l2_")]
    grouped = {
        str(symbol): part
        for symbol, part in table.groupby(table["symbol"].astype(str).str.upper(), sort=False)
    }
    for key, symbol, frame in selected:
        part = grouped.get(symbol)
        if part is None or not factor_columns:
            continue
        output[key] = _align(frame, sessions[key], part, factor_columns)
    return output


def _identities(members: list[dict]) -> dict[str, tuple[str, str]]:
    identities: dict[str, tuple[str, str]] = {}
    for item in members:
        symbol = canonical_symbol(item.get("symbol") or item.get("key") or "")
        market = str(item.get("market") or "")
        key = str(item.get("key") or "")
        if key:
            identities[key] = (market, symbol)
        raw_symbol = str(item.get("symbol") or "").upper()
        if raw_symbol:
            identities[raw_symbol] = (market, symbol)
    return identities


def _is_china_stock(market: str, symbol: str) -> bool:
    if market and market != "CNStock":
        return False
    return symbol.endswith(_CN_SUFFIX)


def _with_rollups(table: pd.DataFrame) -> pd.DataFrame:
    """基础序列已经按股票拼好之后才算滚动列。"""
    from app.services.level2_factors.rollup import add_rollups

    return add_rollups(table)


def _load_symbol_base_d1(symbol: str, needed: list[str]) -> pd.DataFrame:
    """一只股票：本地 SQLite 优先，缺口再打 D1 并回写。"""
    code = canonical_symbol(symbol)
    dates = _dates_for_window_d1(needed, symbol=code)
    rows = _fetch_d1_with_local([code], dates)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _load_cross_section_d1(symbols: list[str], needed: list[str]) -> pd.DataFrame:
    """多只股票：本地 SQLite 优先，缺口再打 D1 并回写。"""
    codes = sorted({canonical_symbol(item) for item in symbols})
    dates = _dates_for_window_d1(needed, symbol=codes[0] if codes else None)
    rows = _fetch_d1_with_local(codes, dates)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _fetch_d1_with_local(symbols: list[str], dates: list[str]) -> list[dict]:
    """先读本地缓存，缺的 (symbol, date) 再问 D1，有行则回写 SQLite。"""
    from app.services.level2_factors import d1_factors, local_d1_cache

    codes = sorted({str(item).upper() for item in symbols if str(item).strip()})
    days = sorted({str(item) for item in dates if str(item).strip()})
    if not codes or not days:
        return []
    local_rows = local_d1_cache.fetch(codes, days)
    have = {
        (str(row.get("symbol") or "").upper(), str(row.get("trade_date") or ""))
        for row in local_rows
    }
    missing_codes = sorted({
        code for code in codes for day in days if (code, day) not in have
    })
    missing_days = sorted({
        day for code in codes for day in days if (code, day) not in have
    })
    remote_rows: list[dict] = []
    if missing_codes and missing_days:
        try:
            remote_rows = d1_factors.fetch_symbols(missing_codes, missing_days)
        except Exception:
            _log.warning("Level2 从 D1 读取失败 symbols=%s", missing_codes[:5], exc_info=True)
            remote_rows = []
        if remote_rows:
            local_d1_cache.upsert_rows(remote_rows)
    # 合并时远端覆盖同键（刚回写的权威值）。
    merged: dict[tuple[str, str], dict] = {}
    for row in local_rows:
        key = (str(row.get("symbol") or "").upper(), str(row.get("trade_date") or ""))
        if key[0] and key[1]:
            merged[key] = row
    for row in remote_rows:
        key = (str(row.get("symbol") or "").upper(), str(row.get("trade_date") or ""))
        if key[0] and key[1]:
            merged[key] = row
    return list(merged.values())


def _dates_for_window_d1(needed: list[str], *, symbol: str | None = None) -> list[str]:
    if not needed:
        return []
    first = min(needed)
    prior = _warmup_dates_d1(first, symbol=symbol)
    return sorted(set(prior) | set(needed))


def _warmup_dates_d1(before: str, *, symbol: str | None = None) -> list[str]:
    """预热日优先本地 SQLite；不足再问 D1。"""
    from app.services.level2_factors import d1_client, d1_factors, local_d1_cache

    try:
        if symbol:
            local = local_d1_cache.warmup_dates(symbol, before, _WARMUP_DAYS)
            if len(local) >= _WARMUP_DAYS:
                return local
            remote = d1_factors.warmup_dates(symbol, before, _WARMUP_DAYS)
            return sorted(set(local) | set(remote))[-_WARMUP_DAYS:]
        # 无 symbol 时无法用本地按股索引，仍问 D1 全局 distinct。
        rows = d1_client.query(
            "SELECT DISTINCT trade_date AS trade_date FROM l2_factors "
            "WHERE trade_date < ? ORDER BY trade_date DESC LIMIT ?",
            [str(before), _WARMUP_DAYS],
        )
        return sorted(str(row["trade_date"]) for row in rows if row.get("trade_date"))
    except Exception:
        _log.warning("Level2 预热日期查询失败", exc_info=True)
        return []


# --- 以下仅供单测 ``directory=`` 注入 ---


def _load_symbol_base_local(directory: Path, symbol: str, needed: list[str]) -> pd.DataFrame:
    code = canonical_symbol(symbol)
    frames: list[pd.DataFrame] = []
    have: set[str] = set()
    mirror_path = Path(directory) / "symbol" / f"{code}.parquet"
    if mirror_path.is_file():
        try:
            mirror = pd.read_parquet(mirror_path)
            if "trade_date" in mirror.columns:
                mirror["trade_date"] = mirror["trade_date"].astype(str)
            if "symbol" in mirror.columns:
                mirror["symbol"] = mirror["symbol"].astype(str).str.upper()
            part = mirror.loc[mirror["symbol"] == code]
            if not part.empty:
                frames.append(part)
                have = set(part["trade_date"].astype(str))
        except Exception:
            _log.warning("Level2 测试镜像读取失败 %s", mirror_path, exc_info=True)
    fetch = [day for day in _dates_for_window_local(directory, needed) if day not in have]
    if fetch:
        daily = _load_dates_local(directory, fetch)
        if not daily.empty and "symbol" in daily.columns:
            rows = daily.loc[daily["symbol"].astype(str).str.upper() == code]
            if not rows.empty:
                frames.append(rows)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _load_cross_section_local(directory: Path, symbols: list[str], needed: list[str]) -> pd.DataFrame:
    wanted = {canonical_symbol(item) for item in symbols}
    table = _load_dates_local(directory, _dates_for_window_local(directory, needed))
    if table.empty or "symbol" not in table.columns:
        return pd.DataFrame()
    return table.loc[table["symbol"].astype(str).str.upper().isin(wanted)].copy()


def _dates_for_window_local(directory: Path, needed: list[str]) -> list[str]:
    if not needed:
        return []
    first = min(needed)
    local = [
        path.stem
        for path in Path(directory).glob("*.parquet")
        if path.stem.isdigit() and len(path.stem) == 8 and path.stem < first
    ]
    prior = sorted(local)[-_WARMUP_DAYS:]
    return sorted(set(prior) | set(needed))


def _load_dates_local(directory: Path, dates: list[str]) -> pd.DataFrame:
    frames = []
    for date in dates:
        day = _read_day_local(directory, date)
        if day is not None and not day.empty:
            frames.append(day)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _read_day_local(directory: Path, date: str) -> pd.DataFrame | None:
    cache_key = (f"local:{Path(directory)}", date)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    file_path = Path(directory) / f"{date}.parquet"
    if not file_path.is_file():
        _CACHE[cache_key] = None
        return None
    try:
        frame = pd.read_parquet(file_path)
    except Exception:
        _log.warning("Level2 测试面板读取失败 %s", file_path, exc_info=True)
        _CACHE[cache_key] = None
        return None
    if "trade_date" in frame.columns:
        frame["trade_date"] = frame["trade_date"].astype(str)
    if "symbol" in frame.columns:
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
    _CACHE[cache_key] = frame
    return frame


def _align(
    frame: pd.DataFrame,
    session: pd.DatetimeIndex,
    part: pd.DataFrame,
    factor_columns: list[str],
) -> pd.DataFrame:
    """同一交易日精确匹配，不向前填充，避免用上一交易日冒充当日因子。"""
    observations = part.drop_duplicates("trade_date", keep="last").copy()
    stamps = pd.to_datetime(observations["trade_date"], format="%Y%m%d", errors="coerce")
    observations = observations.loc[stamps.notna()].copy()
    stamps = stamps.loc[stamps.notna()]
    lookups = {
        column: dict(zip(
            stamps,
            pd.to_numeric(observations[column], errors="coerce") if column in observations.columns else [],
        ))
        for column in factor_columns
    }
    enriched = frame.copy()
    keys = list(pd.DatetimeIndex(session))
    for column in factor_columns:
        table = lookups[column]
        enriched[column] = [table.get(stamp, float("nan")) for stamp in keys]
    return enriched
