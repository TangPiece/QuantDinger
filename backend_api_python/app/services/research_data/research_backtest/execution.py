"""信号日 → 执行日映射（ResearchExecutionPolicy）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from .calendar import next_trading_day
from .protocol import ResearchExecutionPolicy


def map_targets_to_execution(
    targets_by_signal_date: Mapping[date, Sequence[Mapping[str, Any]]],
    calendar: Sequence[date],
    policy: ResearchExecutionPolicy,
) -> dict[date, dict[str, float]]:
    """将信号日目标权重映射到执行日；同 instrument 后者覆盖。

    返回 ``{execution_date: {instrument_key: target_weight}}``。
    """
    out: dict[date, dict[str, float]] = {}
    for signal_date in sorted(targets_by_signal_date.keys()):
        rows = targets_by_signal_date[signal_date]
        if policy.mode == "SAME_CLOSE":
            exec_date = signal_date
        else:
            nxt = next_trading_day(calendar, signal_date)
            if nxt is None:
                continue
            exec_date = nxt
        if exec_date not in calendar:
            # 执行日落在回测窗口外则丢弃
            continue
        bucket = out.setdefault(exec_date, {})
        for row in rows:
            key = str(row.get("instrument_key") or "").strip()
            if not key:
                continue
            w = row.get("target_weight")
            if w is None:
                continue
            try:
                wf = float(w)
            except (TypeError, ValueError):
                continue
            if wf != wf:  # NaN
                continue
            bucket[key] = wf
    return out
