"""按日加载明细并计算指定因子组。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.level2_factors.book import book_path, list_equity_codes, load_book
from app.services.level2_factors.prep import is_equity

from .catalog import (
    GROUP_BOOK,
    GROUP_MICROSTRUCTURE,
    GROUP_ORDER,
    GROUP_TRADE,
    factor_ids_for_group,
)
from .groups import (
    calc_book_factors,
    calc_microstructure_factors,
    calc_order_factors,
    calc_trade_factors,
)

_log = logging.getLogger(__name__)


def list_codes(parquet_root: Path, trade_date: str) -> list[str]:
    codes = list_equity_codes(parquet_root, trade_date)
    if codes:
        return codes
    day = Path(parquet_root) / str(trade_date)
    if not day.is_dir():
        return []
    return sorted(
        child.name
        for child in day.iterdir()
        if child.is_dir() and is_equity(child.name)
    )


def calc_group_for_symbol(
    parquet_root: Path,
    trade_date: str,
    code: str,
    factor_group: str,
) -> dict[str, Any] | None:
    """计算一只股票一个组；缺关键输入返回 None（调用方记 fail/skip）。"""
    try:
        if factor_group == GROUP_TRADE:
            trades = _read_local(parquet_root, trade_date, code, "逐笔成交")
            row = calc_trade_factors(trades, code)
        elif factor_group == GROUP_BOOK:
            snap = _read_local(parquet_root, trade_date, code, "行情")
            row = calc_book_factors(snap)
        elif factor_group == GROUP_ORDER:
            orders = _optional_frame(parquet_root, trade_date, code, "逐笔委托")
            trades = _optional_frame(parquet_root, trade_date, code, "逐笔成交")
            if orders.empty and trades.empty:
                return None
            row = calc_order_factors(orders, trades, code)
        elif factor_group == GROUP_MICROSTRUCTURE:
            frames = _load_any(parquet_root, trade_date, code)
            if frames is None:
                return None
            row = calc_microstructure_factors(
                frames["行情"], frames["逐笔成交"], frames["逐笔委托"], code
            )
        else:
            raise ValueError(f"unknown factor_group: {factor_group}")
    except FileNotFoundError:
        return None
    except Exception:
        _log.warning("l2_daily 计算失败 %s %s %s", trade_date, code, factor_group, exc_info=True)
        return None
    row["trade_date"] = str(trade_date)
    row["symbol"] = str(code)
    return row


def calc_group_day(
    parquet_root: Path,
    trade_date: str,
    factor_group: str,
    *,
    codes: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """返回 (factor_rows, status_rows, ok, fail)。"""
    selected = codes if codes is not None else list_codes(parquet_root, trade_date)
    rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    ok = 0
    fail = 0
    columns = factor_ids_for_group(factor_group)
    for code in selected:
        result = calc_group_for_symbol(parquet_root, trade_date, code, factor_group)
        if result is None:
            fail += 1
            status_rows.append(
                {
                    "symbol": code,
                    "factor_group": factor_group,
                    "status": "failed",
                    "source_version": "",
                }
            )
            continue
        ok += 1
        # 只保留本组列 + 键
        slim = {"trade_date": trade_date, "symbol": code}
        for column in columns:
            slim[column] = result.get(column, float("nan"))
        rows.append(slim)
        status_rows.append(
            {
                "symbol": code,
                "factor_group": factor_group,
                "status": "done",
                "source_version": "",
            }
        )
    return rows, status_rows, ok, fail


def _read_local(root: Path, date: str, code: str, ftype: str) -> pd.DataFrame:
    """只读本地文件，不触发网盘下载。"""
    path = book_path(root, date, code, ftype)
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)


def _optional_frame(root: Path, date: str, code: str, ftype: str) -> pd.DataFrame:
    try:
        return _read_local(root, date, code, ftype)
    except FileNotFoundError:
        return pd.DataFrame()


def _load_any(root: Path, date: str, code: str) -> dict[str, pd.DataFrame] | None:
    frames = {
        "行情": _optional_frame(root, date, code, "行情"),
        "逐笔成交": _optional_frame(root, date, code, "逐笔成交"),
        "逐笔委托": _optional_frame(root, date, code, "逐笔委托"),
    }
    if all(frame.empty for frame in frames.values()):
        return None
    return frames


def load_full_book(root: Path, date: str, code: str) -> dict[str, pd.DataFrame] | None:
    try:
        return load_book(root, date, code)
    except FileNotFoundError:
        return None
