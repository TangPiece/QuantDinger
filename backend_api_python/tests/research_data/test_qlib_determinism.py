"""同 dataset_hash + materializer_version → 逻辑等价。"""

from __future__ import annotations

from pathlib import Path

from app.services.research_data.qlib_materializer.calendar import read_calendar_day_txt


def test_two_materializations_logical_equivalent(golden_qlib_env):
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    a = mat.materialize(ref, force=True)
    # 第二次应 hit；再 force 重建应得到相同 checksum
    hit = mat.materialize(ref, force=False)
    assert hit.cache_hit is True
    assert hit.materialization_id == a.materialization_id
    assert hit.checksum == a.checksum

    b = mat.materialize(ref, force=True)
    assert b.cache_hit is False
    assert b.materialization_id == a.materialization_id
    assert b.checksum == a.checksum
    assert b.calendar_count == a.calendar_count
    assert b.instrument_count == a.instrument_count

    cal_a = read_calendar_day_txt(Path(a.cache_path) / "calendars" / "day.txt")
    cal_b = read_calendar_day_txt(Path(b.cache_path) / "calendars" / "day.txt")
    assert cal_a == cal_b
