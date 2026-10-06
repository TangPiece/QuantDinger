"""ForwardReturnEngine：唯一远期收益计算入口（评价标签，非 Factor）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import pandas as pd

from .protocol import ReturnSpec


class ForwardReturnError(ValueError):
    """远期收益无法计算。"""


def shift_trading_day(
    calendar: list[date], day: date, n: int
) -> Optional[date]:
    """在交易日历上偏移 n 个交易日；越界返回 None。"""
    if not calendar:
        return None
    try:
        idx = calendar.index(day)
    except ValueError:
        # 非交易日：对齐到下一个可用日再偏移
        later = [d for d in calendar if d >= day]
        if not later:
            return None
        idx = calendar.index(later[0])
    j = idx + int(n)
    if j < 0 or j >= len(calendar):
        return None
    return calendar[j]


class ForwardReturnEngine:
    """按 ReturnSpec 从 market panel 生成 multi-horizon forward returns。"""

    def compute_row_returns(
        self,
        *,
        market_by_key_date: dict[tuple[str, date], dict[str, Any]],
        calendar: list[date],
        instrument_key: str,
        factor_date: date,
        return_spec: ReturnSpec,
    ) -> dict[str, Any]:
        """计算单行 entry/exit 与各 horizon 收益。

        语义：
        - entry_date = factor_date + execution_delay
        - exit_date(h) = factor_date + h（交易日）
        - return = exit_price[exit] / entry_price[entry] - 1
        """
        delay = int(return_spec.execution_delay)
        entry_date = shift_trading_day(calendar, factor_date, delay)
        result: dict[str, Any] = {
            "entry_date": entry_date,
            "exit_date": None,
            "returns": {},
            "status_hint": None,
        }
        if entry_date is None:
            result["status_hint"] = "MISSING_RETURN"
            return result

        # close_to_next_open：exit 为 entry 后下一交易日 open（horizon 仍可多列）
        entry_field = return_spec.entry_price
        exit_field = return_spec.exit_price
        entry_bar = market_by_key_date.get((instrument_key, entry_date))
        if entry_bar is None:
            result["status_hint"] = "PRICE_INVALID"
            return result
        entry_px = entry_bar.get(entry_field)
        if entry_px is None or (
            isinstance(entry_px, float) and entry_px != entry_px
        ) or float(entry_px) == 0.0:
            result["status_hint"] = "PRICE_INVALID"
            return result

        max_exit: Optional[date] = None
        for h in return_spec.horizons:
            if return_spec.definition == "close_to_next_open":
                # overnight：exit = entry_date + 1（忽略 h>1 时仍按 entry+h）
                exit_date = shift_trading_day(calendar, entry_date, max(h, 1))
            else:
                # 用户约定：exit = factor_date + horizon
                exit_date = shift_trading_day(calendar, factor_date, h)
            col = f"forward_return_{h}d"
            if exit_date is None or entry_date > exit_date:
                result["returns"][col] = None
                continue
            if delay >= 1 and not (factor_date < entry_date <= exit_date):
                result["returns"][col] = None
                result["status_hint"] = result["status_hint"] or "MISSING_RETURN"
                continue
            if delay == 0 and not (factor_date <= entry_date <= exit_date):
                result["returns"][col] = None
                continue
            exit_bar = market_by_key_date.get((instrument_key, exit_date))
            if exit_bar is None:
                result["returns"][col] = None
                continue
            exit_px = exit_bar.get(exit_field)
            if exit_px is None or (
                isinstance(exit_px, float) and exit_px != exit_px
            ) or float(exit_px) == 0.0:
                result["returns"][col] = None
                continue
            result["returns"][col] = float(exit_px) / float(entry_px) - 1.0
            if max_exit is None or exit_date > max_exit:
                max_exit = exit_date
        result["exit_date"] = max_exit
        if all(v is None for v in result["returns"].values()):
            result["status_hint"] = result["status_hint"] or "MISSING_RETURN"
        return result

    def build_market_index(self, market: pd.DataFrame) -> dict[tuple[str, date], dict]:
        """(instrument_key, trading_date) → bar dict。"""
        if market is None or market.empty:
            return {}
        out: dict[tuple[str, date], dict] = {}
        for row in market.to_dict(orient="records"):
            ik = str(row["instrument_key"])
            td = row["trading_date"]
            if hasattr(td, "date") and not isinstance(td, date):
                td = td.date()
            elif isinstance(td, str):
                td = date.fromisoformat(td[:10])
            out[(ik, td)] = row
        return out
