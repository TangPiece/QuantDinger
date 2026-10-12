"""按日加载明细并计算指定因子组。优先 CSV，回退 Parquet。"""
from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.level2_factors.book import book_path, list_equity_codes, load_book
from app.services.level2_factors.prep import is_equity
from app.services.level2_ingest.csv_to_parquet import read_csv_bytes

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
_FILE_TYPES = ("行情", "逐笔成交", "逐笔委托")
_PROGRESS_EVERY = 100


def source_file_path(root: Path, date: str, code: str, ftype: str) -> Path | None:
    """优先 CSV，其次 Parquet；都不存在返回 None。"""
    day_code = Path(root) / str(date) / str(code)
    csv_path = day_code / f"{ftype}.csv"
    if csv_path.is_file():
        return csv_path
    parquet_path = book_path(root, date, code, ftype)
    if parquet_path.is_file():
        return parquet_path
    return None


def list_codes(books_root: Path, trade_date: str) -> list[str]:
    """列出当日股票代码：先扫 books_root 日目录，再回退 list_equity_codes。"""
    day = Path(books_root) / str(trade_date)
    if day.is_dir():
        codes = sorted(
            child.name
            for child in day.iterdir()
            if child.is_dir() and is_equity(child.name)
        )
        if codes:
            return codes
    return list_equity_codes(books_root, trade_date)


def calc_group_for_symbol(
    books_root: Path,
    trade_date: str,
    code: str,
    factor_group: str,
) -> dict[str, Any] | None:
    """计算一只股票一个组；缺关键输入返回 None（调用方记 fail/skip）。"""
    try:
        if factor_group == GROUP_TRADE:
            trades = _read_local(books_root, trade_date, code, "逐笔成交")
            row = calc_trade_factors(trades, code)
        elif factor_group == GROUP_BOOK:
            snap = _read_local(books_root, trade_date, code, "行情")
            row = calc_book_factors(snap)
        elif factor_group == GROUP_ORDER:
            orders = _optional_frame(books_root, trade_date, code, "逐笔委托")
            trades = _optional_frame(books_root, trade_date, code, "逐笔成交")
            if orders.empty and trades.empty:
                return None
            row = calc_order_factors(orders, trades, code)
        elif factor_group == GROUP_MICROSTRUCTURE:
            frames = _load_any(books_root, trade_date, code)
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


def calc_group_for_symbol_worker(
    trade_date: str,
    code: str,
    books_root: str,
    factor_group: str,
) -> dict[str, Any] | None:
    """子进程入口：参数均为可 pickle 的基本类型。"""
    return calc_group_for_symbol(Path(books_root), trade_date, code, factor_group)


def _emit_symbol_progress(trade_date: str, factor_group: str, done: int, total: int) -> None:
    """每完成一批股票打印一次，最后一只也打印。"""
    if total <= 0:
        return
    if done == total or done % _PROGRESS_EVERY == 0:
        print(f"[{trade_date}] {factor_group} 已完成 {done}/{total}", flush=True)


def _append_symbol_result(
    *,
    trade_date: str,
    code: str,
    factor_group: str,
    result: dict[str, Any] | None,
    columns: list[str],
    rows: list[dict[str, Any]],
    status_rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """把单股结果写入 rows/status_rows，返回 (ok_delta, fail_delta)。"""
    if result is None:
        status_rows.append(
            {
                "symbol": code,
                "factor_group": factor_group,
                "status": "failed",
                "source_version": "",
            }
        )
        return 0, 1
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
    return 1, 0


def calc_group_day(
    books_root: Path,
    trade_date: str,
    factor_group: str,
    *,
    codes: list[str] | None = None,
    workers: int = 1,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """返回 (factor_rows, status_rows, ok, fail)。

    ``workers`` > 1 且股票数 > 1 时用进程池按股票并行；否则顺序计算。
    """
    selected = codes if codes is not None else list_codes(books_root, trade_date)
    rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    ok = 0
    fail = 0
    columns = factor_ids_for_group(factor_group)
    total = len(selected)
    pool_workers = max(1, int(workers))

    if pool_workers <= 1 or total <= 1:
        for done, code in enumerate(selected, start=1):
            result = calc_group_for_symbol(books_root, trade_date, code, factor_group)
            d_ok, d_fail = _append_symbol_result(
                trade_date=trade_date,
                code=code,
                factor_group=factor_group,
                result=result,
                columns=columns,
                rows=rows,
                status_rows=status_rows,
            )
            ok += d_ok
            fail += d_fail
            _emit_symbol_progress(trade_date, factor_group, done, total)
    else:
        root_str = str(books_root)
        with ProcessPoolExecutor(max_workers=min(pool_workers, total)) as pool:
            futures = [
                pool.submit(
                    calc_group_for_symbol_worker,
                    trade_date,
                    code,
                    root_str,
                    factor_group,
                )
                for code in selected
            ]
            for done, (code, future) in enumerate(zip(selected, futures), start=1):
                try:
                    result = future.result()
                except Exception:
                    _log.warning(
                        "l2_daily 并行计算异常 %s %s %s",
                        trade_date,
                        code,
                        factor_group,
                        exc_info=True,
                    )
                    result = None
                d_ok, d_fail = _append_symbol_result(
                    trade_date=trade_date,
                    code=code,
                    factor_group=factor_group,
                    result=result,
                    columns=columns,
                    rows=rows,
                    status_rows=status_rows,
                )
                ok += d_ok
                fail += d_fail
                _emit_symbol_progress(trade_date, factor_group, done, total)

    rows.sort(key=lambda item: str(item.get("symbol") or ""))
    status_rows.sort(key=lambda item: str(item.get("symbol") or ""))
    return rows, status_rows, ok, fail


def _read_local(root: Path, date: str, code: str, ftype: str) -> pd.DataFrame:
    """只读本地文件：CSV（规范化）优先，其次 Parquet；不触发网盘下载。"""
    path = source_file_path(root, date, code, ftype)
    if path is None:
        raise FileNotFoundError(Path(root) / str(date) / str(code) / f"{ftype}.csv")
    if path.suffix.lower() == ".csv":
        return read_csv_bytes(path.read_bytes(), ftype)
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
