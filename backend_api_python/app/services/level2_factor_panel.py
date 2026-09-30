"""把离线算好的 Level2 日频 Parquet 按交易日并到 A 股日线上。

目录由环境变量 ``LEVEL2_FACTOR_PANEL_DIR`` 指定，里面每天一个 ``YYYYMMDD.parquet``，
只含基础因子。未配置时用 ``backend_api_python/data/level2_factors``。本地没有该日文件时再向 R2 要一份。
一只股票的图表和 CTA 优先读 ``symbol/{代码}.parquet``，周中新的交易日再从按日文件补。
多只股票的组合回测直接读按日宽表。5/10/20 日滚动列在拼好基础序列后现算。
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
    """项目内因子目录。本机是 ``backend_api_python/data/level2_factors``，容器是 ``/app/data/level2_factors``。"""
    # 本文件在 app/services，往上两级是后端根目录。
    root = Path(__file__).resolve().parents[2] / "data" / "level2_factors"
    root.mkdir(parents=True, exist_ok=True)
    return root


def panel_directory() -> Path:
    """因子 Parquet 目录。环境变量为空时用项目内默认目录，并在需要时创建。"""
    raw = os.getenv("LEVEL2_FACTOR_PANEL_DIR", "").strip()
    path = Path(raw) if raw else default_factor_directory()
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_panel_cache() -> None:
    """测试改写同一路径下的文件后需要清掉已读入的日期。"""
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
    还原成当日交易日，避免和 Parquet 里的 ``YYYYMMDD`` 错一天。
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
    """给 CNStock 日线加上 ``l2_*`` 列。其它市场和未配置目录保持原表。"""
    path = Path(directory) if directory else panel_directory()
    if not path.is_dir():
        return dict(frames)
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
    # 一只股票走镜像；多只要当天截面，走按日宽表。
    if len(symbols) == 1:
        table = _load_symbol_base(path, symbols[0], sorted(needed))
    else:
        table = _load_cross_section(path, symbols, sorted(needed))
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


def symbol_file_path(directory: Path, symbol: str) -> Path:
    """本地股票镜像路径。和按日文件分开，避免把单只结果当成全市场。"""
    return Path(directory) / "symbol" / f"{canonical_symbol(symbol)}.parquet"


def _with_rollups(table: pd.DataFrame) -> pd.DataFrame:
    """基础序列已经按股票拼好之后才算滚动列。文件里旧的滚动列会被丢掉重算。"""
    from app.services.level2_factors.rollup import add_rollups

    return add_rollups(table)


def _load_symbol_base(directory: Path, symbol: str, needed: list[str]) -> pd.DataFrame:
    """一只股票：镜像里的历史，再加上镜像还没有的交易日（含窗口预热）。"""
    code = canonical_symbol(symbol)
    frames: list[pd.DataFrame] = []
    have: set[str] = set()
    mirror = _read_symbol(directory, code)
    if mirror is not None and not mirror.empty and "symbol" in mirror.columns:
        part = mirror.loc[mirror["symbol"].astype(str).str.upper() == code]
        if not part.empty:
            frames.append(part)
            have = set(part["trade_date"].astype(str))
    fetch = [day for day in _dates_for_window(directory, needed) if day not in have]
    if fetch:
        daily = _load_dates(directory, fetch)
        if not daily.empty and "symbol" in daily.columns:
            rows = daily.loc[daily["symbol"].astype(str).str.upper() == code]
            if not rows.empty:
                frames.append(rows)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _load_cross_section(directory: Path, symbols: list[str], needed: list[str]) -> pd.DataFrame:
    """多只股票：按日宽表覆盖回测区间和窗口预热，再留下成分股。"""
    table = _load_dates(directory, _dates_for_window(directory, needed))
    if table.empty or "symbol" not in table.columns:
        return pd.DataFrame()
    wanted = {canonical_symbol(item) for item in symbols}
    return table.loc[table["symbol"].astype(str).str.upper().isin(wanted)].copy()


def _dates_for_window(directory: Path, needed: list[str]) -> list[str]:
    """图表或回测区间，再往前补最多 19 个已有交易日，供 20 日滚动窗口。"""
    if not needed:
        return []
    first = min(needed)
    prior = _warmup_dates(directory, first)
    return sorted(set(prior) | set(needed))


def _warmup_dates(directory: Path, before: str) -> list[str]:
    """``before`` 之前本地已有的交易日，最多 19 个。

    不在这里列举整个桶。股票镜像里的历史已经覆盖预热；还缺的具体日期由按日文件下载补。
    """
    local = [path.stem for path in _day_files(directory) if path.stem < before]
    return local[-_WARMUP_DAYS:]


def _day_files(directory: Path) -> list[Path]:
    """目录根上的按日文件。``symbol/`` 子目录里的镜像不算交易日。"""
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.glob("*.parquet")
        if path.stem.isdigit() and len(path.stem) == 8
    )


def _read_symbol(directory: Path, symbol: str) -> pd.DataFrame | None:
    """读本地股票镜像；没有就向 R2 要一份。失败时当作没有镜像，改走按日文件。"""
    code = canonical_symbol(symbol)
    cache_key = (str(directory.resolve()), f"symbol:{code}")
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    file_path = symbol_file_path(directory, code)
    if not file_path.is_file():
        _pull_symbol(file_path, code)
    if not file_path.is_file():
        _CACHE[cache_key] = None
        return None
    try:
        frame = pd.read_parquet(file_path)
    except Exception:
        _log.warning("Level2 股票镜像读取失败 %s", file_path, exc_info=True)
        _CACHE[cache_key] = None
        return None
    if "trade_date" in frame.columns:
        frame["trade_date"] = frame["trade_date"].astype(str)
    if "symbol" in frame.columns:
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
    _CACHE[cache_key] = frame
    return frame


def _pull_symbol(file_path: Path, symbol: str) -> None:
    """本地没有这只股票的镜像时从 R2 拉下。失败保持没有文件。"""
    from app.services.level2_factors.r2_factors import download_symbol_file

    payload = download_symbol_file(symbol)
    if not payload:
        return
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = file_path.with_suffix(".parquet.part")
    temporary.write_bytes(payload)
    temporary.replace(file_path)


def _load_dates(directory: Path, dates: list[str]) -> pd.DataFrame:
    frames = []
    for date in dates:
        day = _read_day(directory, date)
        if day is not None and not day.empty:
            frames.append(day)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _read_day(directory: Path, date: str) -> pd.DataFrame | None:
    cache_key = (str(directory.resolve()), date)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    file_path = directory / f"{date}.parquet"
    if not file_path.is_file():
        _pull_factor_day(file_path, date)
    if not file_path.is_file():
        _CACHE[cache_key] = None
        return None
    try:
        frame = pd.read_parquet(file_path)
    except Exception:
        # 某一天坏掉或没有 parquet 引擎时跳过，不要让整段副图 500。
        _log.warning("Level2 面板读取失败 %s", file_path, exc_info=True)
        _CACHE[cache_key] = None
        return None
    if "trade_date" in frame.columns:
        frame["trade_date"] = frame["trade_date"].astype(str)
    if "symbol" in frame.columns:
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
    _CACHE[cache_key] = frame
    return frame


def _pull_factor_day(file_path: Path, date: str) -> None:
    """本地没有这一天时，从 R2 拉下 ``{date}.parquet`` 再读。失败保持没有文件。"""
    from app.services.level2_factors.r2_factors import download_factor_file

    payload = download_factor_file(date)
    if not payload:
        return
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = file_path.with_suffix(".parquet.part")
    temporary.write_bytes(payload)
    temporary.replace(file_path)


def _align(
    frame: pd.DataFrame,
    session: pd.DatetimeIndex,
    part: pd.DataFrame,
    factor_columns: list[str],
) -> pd.DataFrame:
    """同一交易日精确匹配，不向前填充，避免用上一交易日冒充当日因子。

    按日期查表而不是 ``reindex``。同一上海交易日有多根 K 线时每根都取到同一个值。
    """
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
