"""PIT leakage：available_time > knowledge_time 的值不可见。"""

from __future__ import annotations

from datetime import datetime, timezone


def test_pit_respects_available_time_and_revision(seeded_research):
    query = seeded_research["query"]
    # 在第一次与第二次修订之间
    mid = datetime(2024, 4, 22, 12, 0, tzinfo=timezone.utc)
    df = query.fundamental(["CNStock:000001"], ["ROE"], mid, exchange="CN")
    assert len(df) == 1
    assert float(df.iloc[0]["value"]) == 10.1
    assert int(df.iloc[0]["revision"]) == 0

    after_second = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    df2 = query.fundamental(["CNStock:000001"], ["ROE"], after_second, exchange="CN")
    assert float(df2.iloc[0]["value"]) == 10.4
    assert int(df2.iloc[0]["revision"]) == 1

    after_restatement = datetime(2024, 9, 1, 12, 0, tzinfo=timezone.utc)
    df3 = query.fundamental(["CNStock:000001"], ["ROE"], after_restatement, exchange="CN")
    assert float(df3.iloc[0]["value"]) == 10.7
    assert int(df3.iloc[0]["revision"]) == 2


def test_pit_no_future_rows_leak(seeded_research):
    query = seeded_research["query"]
    before_any = datetime(2024, 4, 1, tzinfo=timezone.utc)
    df = query.fundamental(["CNStock:000001"], ["ROE"], before_any, exchange="CN")
    assert df.empty
