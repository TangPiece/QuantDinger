"""强制经 pyqlib API 读回（via=qlib 且 sample_rows>0）。"""

from __future__ import annotations

from pathlib import Path

import pytest

qlib = pytest.importorskip("qlib")

from app.services.research_data.qlib_materializer.validation import validate_qlib_provider


def test_qlib_provider_readback_nonempty(golden_qlib_env):
    mat = golden_qlib_env["materializer"]
    result = mat.materialize(golden_qlib_env["dataset_ref"], force=True)
    out = validate_qlib_provider(
        Path(result.cache_path),
        expect_calendar_count=result.calendar_count,
        expect_instrument_count=result.instrument_count,
        sample_instrument="sz000001",
        sample_field="close",
    )
    assert out["via"] == "qlib"
    assert int(out["sample_rows"]) > 0
    assert out["qlib_calendar_count"] == result.calendar_count
