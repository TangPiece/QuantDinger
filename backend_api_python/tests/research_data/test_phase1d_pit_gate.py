"""Phase 1D：PIT 门禁 — DataQuery + Materializer 边界 + pit-safe panel。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pyarrow as pa

from app.services.research_data.phase1d_panel import build_pit_safe_research_panel
from app.services.research_data.writer import write_pit_fundamental


def test_pit_narrative_april30_visibility(seeded_research):
    """叙事：available_time=2024-04-30 → KT=04-29 不可见，KT=05-01 可见。"""
    store = seeded_research["store"]
    registry = seeded_research["registry"]
    query = seeded_research["query"]

    # 追加一条 classic 叙事行（与修订链并存）
    pit = pa.table(
        {
            "instrument_key": ["CNStock:000002"],
            "metric_code": ["ROE"],
            "report_period_start": [date(2023, 10, 1)],
            "report_period_end": [date(2023, 12, 31)],
            "fiscal_year": [2023],
            "fiscal_quarter": [4],
            "publish_time": [datetime(2024, 4, 30, 15, 0, tzinfo=timezone.utc)],
            "available_time": [datetime(2024, 4, 30, 15, 0, tzinfo=timezone.utc)],
            "value": [12.5],
            "unit": ["pct"],
            "currency": ["CNY"],
            "revision": [0],
            "is_restatement": [False],
            "source": ["narrative"],
            "source_record_id": ["narrative-apr30"],
            "data_version": ["v1"],
        }
    )
    write_pit_fundamental(
        store, pit, exchange="CN", year=2024, registry=registry, version="2024.pit.narrative"
    )

    before = datetime(2024, 4, 29, 12, 0, tzinfo=timezone.utc)
    df_before = query.fundamental(["CNStock:000002"], ["ROE"], before, exchange="CN")
    assert df_before.empty

    after = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    df_after = query.fundamental(["CNStock:000002"], ["ROE"], after, exchange="CN")
    assert len(df_after) == 1
    assert float(df_after.iloc[0]["value"]) == 12.5


def test_materializer_never_calls_fundamental(golden_qlib_env):
    """物化路径不得绕过 DataQuery.fundamental / 不得读 PIT。"""
    query = golden_qlib_env["query"]
    mat = golden_qlib_env["materializer"]
    spy = MagicMock(wraps=query.fundamental)
    query.fundamental = spy  # type: ignore[method-assign]

    mat.materialize(golden_qlib_env["dataset_ref"], force=True)
    spy.assert_not_called()


def test_pit_safe_panel_respects_knowledge_time(seeded_research):
    """研究面板：KT 前看不到未来 ROE；KT 后可见。"""
    query = seeded_research["query"]

    mid = datetime(2024, 4, 22, 12, 0, tzinfo=timezone.utc)
    panel = build_pit_safe_research_panel(
        query,
        ["CNStock:000001"],
        ["ROE"],
        mid,
        market_start=date(2024, 5, 1),
        market_end=date(2024, 5, 1),
    )
    assert len(panel) == 1
    assert float(panel.iloc[0]["ROE"]) == 10.1

    before_any = datetime(2024, 4, 1, tzinfo=timezone.utc)
    panel_empty = build_pit_safe_research_panel(
        query,
        ["CNStock:000001"],
        ["ROE"],
        before_any,
        market_start=date(2024, 5, 1),
        market_end=date(2024, 5, 1),
    )
    assert panel_empty["ROE"].isna().all()

    # 直接 fundamental 在 mid 不应含 revision>=1
    fund = query.fundamental(["CNStock:000001"], ["ROE"], mid, exchange="CN")
    assert int(fund.iloc[0]["revision"]) == 0
