"""因子 / 远期收益 / Universe / 停牌对齐，产出带 SampleStatus 的评价行。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

import pandas as pd

from .forward_return import ForwardReturnEngine
from .protocol import EvaluationFrame, EvaluationPlan, EvaluationSpec, SampleStatus


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _is_nan(v: Any) -> bool:
    if v is None:
        return True
    try:
        return v != v  # NaN
    except Exception:
        return False


class EvaluationAligner:
    """将 Factor 面板与 Forward Return / Universe / Status 对齐。"""

    def __init__(self, engine: ForwardReturnEngine | None = None) -> None:
        self._ret = engine or ForwardReturnEngine()

    def align(
        self,
        *,
        plan: EvaluationPlan,
        spec: EvaluationSpec,
        factor_rows: Sequence[dict[str, Any]],
        market: pd.DataFrame,
        calendar: list[date],
        universe_members: set[str],
        suspended: set[tuple[str, date]] | None = None,
        pit_invalid: set[tuple[str, date]] | None = None,
    ) -> EvaluationFrame:
        """对齐并标注 sample_status；默认保留非 VALID 行。"""
        suspended = suspended or set()
        pit_invalid = pit_invalid or set()
        midx = self._ret.build_market_index(market)
        horizons = list(plan.return_spec.horizons)
        records: list[dict[str, Any]] = []

        for fr in factor_rows:
            ik = str(fr["instrument_key"])
            fd = _as_date(fr.get("factor_date") or fr.get("trading_date"))
            if fd < date.fromisoformat(plan.start_date) or fd > date.fromisoformat(
                plan.end_date
            ):
                continue
            fval = fr.get("factor_value", fr.get("value"))
            status: SampleStatus = "VALID"
            row: dict[str, Any] = {
                "instrument_key": ik,
                "factor_date": fd,
                "factor_value": None if _is_nan(fval) else float(fval),
                "entry_date": None,
                "exit_date": None,
                "universe_code": plan.universe_code,
                "snapshot_id": plan.snapshot_id,
                "mode": plan.mode,
            }
            for h in horizons:
                row[f"forward_return_{h}d"] = None

            if (ik, fd) in pit_invalid or fr.get("pit_invalid"):
                status = "PIT_INVALID"
            elif ik not in universe_members:
                status = "OUT_OF_UNIVERSE"
            elif _is_nan(fval):
                status = "MISSING_FACTOR"
            else:
                ret = self._ret.compute_row_returns(
                    market_by_key_date=midx,
                    calendar=calendar,
                    instrument_key=ik,
                    factor_date=fd,
                    return_spec=plan.return_spec,
                )
                row["entry_date"] = ret["entry_date"]
                row["exit_date"] = ret["exit_date"]
                for col, val in ret["returns"].items():
                    row[col] = val
                # 停牌：entry 或任一 exit 日停牌 → SUSPENDED（不填 0%）
                entry_d = ret["entry_date"]
                exit_d = ret["exit_date"]
                susp = False
                if entry_d and (ik, entry_d) in suspended:
                    susp = True
                if exit_d and (ik, exit_d) in suspended:
                    susp = True
                # 检查各 horizon exit
                for h in horizons:
                    ed = None
                    from .forward_return import shift_trading_day

                    if plan.return_spec.definition == "close_to_next_open" and entry_d:
                        ed = shift_trading_day(calendar, entry_d, max(h, 1))
                    else:
                        ed = shift_trading_day(calendar, fd, h)
                    if ed and (ik, ed) in suspended:
                        susp = True
                        row[f"forward_return_{h}d"] = None
                if susp:
                    status = "SUSPENDED"
                    for h in horizons:
                        row[f"forward_return_{h}d"] = None
                elif ret.get("status_hint") == "PRICE_INVALID":
                    status = "PRICE_INVALID"
                elif ret.get("status_hint") == "MISSING_RETURN":
                    status = "MISSING_RETURN"
                elif all(row.get(f"forward_return_{h}d") is None for h in horizons):
                    status = "MISSING_RETURN"

            row["sample_status"] = status
            # missing policy drop
            if (
                status == "MISSING_FACTOR"
                and spec.missing_data_policy.factor == "drop"
            ):
                continue
            if (
                status in ("MISSING_RETURN", "PRICE_INVALID")
                and spec.missing_data_policy.return_ == "drop"
            ):
                continue
            records.append(row)

        return EvaluationFrame.from_records(
            records, horizons=horizons, mode=plan.mode
        )


def collect_suspended_from_status(
    status_df: pd.DataFrame,
) -> set[tuple[str, date]]:
    """从 trading_status 面板提取停牌键。"""
    out: set[tuple[str, date]] = set()
    if status_df is None or status_df.empty:
        return out
    for r in status_df.to_dict(orient="records"):
        if r.get("is_suspended"):
            out.add((str(r["instrument_key"]), _as_date(r["trading_date"])))
    return out
