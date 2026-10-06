"""Look-ahead 硬校验：execution_time 必须严格晚于 knowledge_time。"""

from __future__ import annotations

from typing import Sequence

from app.services.research_data.contracts import Signal


class LookAheadError(ValueError):
    """检测到隐性 look-ahead。"""


def assert_no_lookahead(signals: Sequence[Signal]) -> None:
    """任一 execution_time <= knowledge_time 则硬失败。"""
    for s in signals:
        if s.execution_time is None or s.knowledge_time is None:
            raise LookAheadError(
                f"missing PIT timestamps for signal {s.signal_id}"
            )
        if s.execution_time <= s.knowledge_time:
            raise LookAheadError(
                f"look-ahead: execution_time <= knowledge_time "
                f"for {s.instrument_key} @ {s.trading_date}"
            )
