"""DataQuery 不得调用实时行情 / HTTP。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest


def test_market_and_universe_do_not_call_requests(seeded_research, monkeypatch):
    query = seeded_research["query"]

    def boom(*_a, **_k):
        raise AssertionError("DataQuery must not call requests")

    monkeypatch.setattr("requests.get", boom)
    monkeypatch.setattr("requests.post", boom)
    monkeypatch.setattr("requests.request", boom)

    # 若误 import 行情服务，也拦住常见入口
    import sys

    for name in list(sys.modules):
        if "market_data" in name or "global_market_data" in name:
            monkeypatch.setattr(
                sys.modules[name],
                "get_price",
                boom,
                raising=False,
            )

    df = query.market(
        ["CNStock:000001"],
        date(2024, 5, 1),
        date(2024, 5, 1),
        exchange="CN",
    )
    assert len(df) == 1
    assert float(df.iloc[0]["close"]) == 10.5

    members = query.universe(
        "CSI300",
        datetime(2024, 6, 1, tzinfo=timezone.utc),
        snapshot_id=seeded_research["snapshot_id"],
        universe_version="2024.05",
    )
    assert "CNStock:000001" in members
    assert "CNStock:999999" not in members  # valid_to 已结束


def test_price_policy_non_none_rejected(seeded_research):
    from app.services.research_data.contracts import PricePolicy

    query = seeded_research["query"]
    with pytest.raises(NotImplementedError):
        query.market(
            ["CNStock:000001"],
            date(2024, 5, 1),
            date(2024, 5, 1),
            price_policy=PricePolicy(adjustment="post"),
        )
