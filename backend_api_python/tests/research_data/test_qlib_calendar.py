"""Calendar：DataQuery 派生序列 == Qlib cache day.txt。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.research_data.qlib_materializer.calendar import read_calendar_day_txt


def test_calendar_matches_dataquery(golden_qlib_env):
    query = golden_qlib_env["query"]
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    handle = query.dataset(ref)
    instruments = query.universe(
        handle.definition.universe_code,
        date(2024, 6, 1),
        snapshot_id=handle.definition.snapshot_id,
        universe_version=handle.definition.universe_version,
    )
    dq_cal = query.trading_calendar(
        instruments,
        date(1970, 1, 1),
        date(2100, 1, 1),
        price_policy=handle.definition.price_policy,
    )
    result = mat.materialize(ref)
    file_cal = read_calendar_day_txt(Path(result.cache_path) / "calendars" / "day.txt")

    assert len(file_cal) == len(dq_cal) == result.calendar_count
    assert file_cal == dq_cal
    assert file_cal == sorted(file_cal)
    assert len(file_cal) == len(set(file_cal))
    assert min(file_cal) == dq_cal[0]
    assert max(file_cal) == dq_cal[-1]
