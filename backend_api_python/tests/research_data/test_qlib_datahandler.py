"""DataHandlerLP / OHLCV 面板可读。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("qlib")

from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.validation import validate_datahandler


def test_datahandler_ohlcv_fetch(golden_qlib_env):
    query = golden_qlib_env["query"]
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    handle = query.dataset(ref)
    result = mat.materialize(ref, force=True)

    from datetime import date

    members = query.universe(
        handle.definition.universe_code,
        date(2024, 3, 1),
        snapshot_id=handle.definition.snapshot_id,
        universe_version=handle.definition.universe_version,
    )
    cal = query.trading_calendar(
        members,
        date(1970, 1, 1),
        date(2100, 1, 1),
        price_policy=handle.definition.price_policy,
    )
    insts = [to_qlib_instrument(ik).lower() for ik in members]
    out = validate_datahandler(
        Path(result.cache_path),
        instruments=insts,
        start=cal[0].isoformat(),
        end=cal[-1].isoformat(),
    )
    assert out["rows"] > 0
    flat = " ".join(out["columns"]).lower()
    assert "close" in flat
    assert "open" in flat
    assert "volume" in flat
