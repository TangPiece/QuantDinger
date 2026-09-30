"""把回测结果里的标的代码映射成本地证券名称。

界面按「代码 + 百分比」展示调仓权重。名称写在 ``symbolNames``，
不改 ``targetWeights`` / ``actualWeights`` 的 key，避免仓位标识被显示文案污染。
只查 ``qd_market_symbols``，回测返回路径不访问外部行情源。
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Mapping

from app.utils.logger import get_logger

from .instruments import InstrumentParseError, infer_market, parse_instrument


logger = get_logger(__name__)

# 与前端 formatSymbolCode 一致：先去掉多空后缀，再去掉市场前缀和交易所后缀。
_SIDE_SUFFIX = re.compile(r"::(?:long|short)$", re.IGNORECASE)
_CN_SUFFIXES = (".SH", ".SZ", ".BJ")
_LOOKUP_CHUNK = 200

NameLookup = Callable[[Iterable[tuple[str, str]]], Mapping[tuple[str, str], str]]


def display_symbol_code(raw: object) -> str:
    """返回回测表格里应打印的代码。

    只去掉已知市场前缀、多空后缀和 ``@交易所``。
    ``Crypto:BTC/USDT@binance:spot`` 得到 ``BTC/USDT``，而不是最后一个冒号后的 ``spot``。
    """
    text = _SIDE_SUFFIX.sub("", str(raw or "").strip())
    if not text:
        return ""
    try:
        return parse_instrument(text).symbol
    except InstrumentParseError:
        if ":" in text:
            prefix, rest = text.split(":", 1)
            if prefix.lower() in {"cnstock", "usstock", "hkstock", "crypto", "forex", "futures", "moex"}:
                text = rest
        return text.split("@")[0].upper()


def attach_symbol_names(
    result: dict[str, Any],
    *,
    default_market: str = "",
    lookup: NameLookup | None = None,
) -> dict[str, Any]:
    """为结果补上 ``symbolNames``。

    key 是界面上的代码，value 是本地名称。查不到、或名称只是代码本身时不写入。
    ``lookup`` 仅供测试注入；默认一次批量读取 ``qd_market_symbols``。
    """
    if not isinstance(result, dict):
        return result
    refs = _collect_symbol_refs(result)
    if not refs:
        return result

    market_hint = _single_market(default_market)
    plans: list[tuple[str, str, list[str]]] = []
    queries: list[tuple[str, str]] = []
    for raw in refs:
        display = display_symbol_code(raw)
        if not display:
            continue
        market, symbol = _parse_market_symbol(raw, market_hint)
        candidates = _candidate_symbols(market, symbol or display)
        plans.append((display, market, candidates))
        for candidate in candidates:
            if market and candidate:
                queries.append((market, candidate))

    resolved = (lookup or _lookup_local_names)(queries)
    names: dict[str, str] = {}
    for display, market, candidates in plans:
        name = _first_usable_name(resolved, market, display, candidates)
        if name:
            names[display] = name
    if names:
        result["symbolNames"] = names
    return result


def _collect_symbol_refs(result: Mapping[str, Any]) -> list[str]:
    """收集调仓、持仓、成交、账本和归因里出现过的标的，保持首次出现顺序。"""
    found: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        found.append(text)

    for record in _dict_list(result.get("rebalanceRecords")):
        for field in ("targetWeights", "actualWeights"):
            weights = record.get(field)
            if isinstance(weights, Mapping):
                for key in weights:
                    add(key)
    for snapshot in _dict_list(result.get("holdingSnapshots")):
        positions = snapshot.get("positions")
        if isinstance(positions, Mapping):
            for key in positions:
                add(key)
    positions = result.get("positions")
    if isinstance(positions, Mapping):
        for key in positions:
            add(key)
    for field in ("closedTrades", "trades", "executions", "rawTrades", "orderLedger"):
        for item in _dict_list(result.get(field)):
            add(item.get("symbol") or item.get("position_key"))
    attribution = result.get("attribution")
    if isinstance(attribution, Mapping):
        for item in _dict_list(attribution.get("symbols")):
            add(item.get("symbol"))
    return found


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _single_market(value: object) -> str:
    """逗号分隔或多市场回测没有唯一默认市场，交给代码自身推断。"""
    raw = str(value or "").strip()
    if not raw or "," in raw or raw.lower() == "mixed":
        return ""
    return raw


def _parse_market_symbol(raw: object, default_market: str) -> tuple[str, str]:
    text = _SIDE_SUFFIX.sub("", str(raw or "").strip())
    try:
        spec = parse_instrument(text, default_market=default_market)
    except InstrumentParseError:
        symbol = display_symbol_code(text)
        return infer_market(symbol) or default_market, symbol
    return spec.market, spec.symbol


def _candidate_symbols(market: str, symbol: str) -> list[str]:
    """A 股代码在种子表里可能带 ``.SH/.SZ/.BJ``，裸代码和带后缀都要能对上。"""
    raw = str(symbol or "").strip().upper()
    if not raw:
        return []
    candidates = [raw]
    bare = raw
    for suffix in (*_CN_SUFFIXES, ".HK"):
        if bare.endswith(suffix):
            bare = bare[: -len(suffix)]
            candidates.append(bare)
            break
    if market == "CNStock" and re.fullmatch(r"\d{6}", bare):
        candidates.extend(f"{bare}{suffix}" for suffix in _CN_SUFFIXES)
    if market == "HKStock" and re.fullmatch(r"\d{1,5}", bare):
        candidates.append(f"{bare}.HK")
    if market == "Crypto" and "/" not in raw:
        candidates.append(f"{raw}/USDT")
    unique: list[str] = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique


def _first_usable_name(
    resolved: Mapping[tuple[str, str], str],
    market: str,
    display: str,
    candidates: list[str],
) -> str:
    for candidate in candidates:
        name = str(resolved.get((market, candidate.upper())) or "").strip()
        if _usable_name(name, display, candidate):
            return name
    return ""


def _usable_name(name: str, display: str, candidate: str) -> bool:
    """名称与代码相同（常见于加密货币回退）时不展示，避免 ``BTC BTC``。"""
    if not name:
        return False
    folded = name.upper()
    return folded not in {display.upper(), candidate.upper(), display_symbol_code(candidate).upper()}


def _lookup_local_names(pairs: Iterable[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """按市场和代码批量读取本地名称。数据库不可用时返回空，不阻断回测。"""
    wanted = {
        (str(market or "").strip(), str(symbol or "").strip().upper())
        for market, symbol in pairs
        if str(market or "").strip() and str(symbol or "").strip()
    }
    if not wanted:
        return {}
    symbols = sorted({symbol for _, symbol in wanted})
    found: dict[tuple[str, str], str] = {}
    try:
        from app.utils.db import get_db_connection

        with get_db_connection() as db:
            cur = db.cursor()
            for offset in range(0, len(symbols), _LOOKUP_CHUNK):
                chunk = symbols[offset:offset + _LOOKUP_CHUNK]
                marks = ",".join(["?"] * len(chunk))
                cur.execute(
                    f"""
                    SELECT market, symbol, name
                    FROM qd_market_symbols
                    WHERE UPPER(symbol) IN ({marks})
                    """,
                    tuple(chunk),
                )
                for row in cur.fetchall() or []:
                    market = str(row.get("market") or "").strip()
                    symbol = str(row.get("symbol") or "").strip().upper()
                    name = str(row.get("name") or "").strip()
                    if market and symbol and name and (market, symbol) in wanted:
                        found[(market, symbol)] = name
            cur.close()
    except Exception as exc:
        logger.debug("symbol name lookup skipped: %s", exc)
        return {}
    return found
