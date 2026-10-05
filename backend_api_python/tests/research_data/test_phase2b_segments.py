"""Phase 2B：SegmentSpec 时间顺序校验。"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.services.research_data.qlib_adapter import ResearchDatasetSpec, SegmentRange, SegmentSpec


def _ok_segments() -> SegmentSpec:
    return SegmentSpec(
        train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
        test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
    )


def test_segment_order_ok():
    seg = _ok_segments()
    assert seg.to_qlib_segments()["train"][0] == "2024-01-01"
    win = seg.handler_window()
    assert win == (date(2024, 1, 1), date(2024, 6, 30))


def test_segment_overlap_fails():
    with pytest.raises(ValidationError):
        SegmentSpec(
            train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 3, 15)),
            valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
            test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
        )


def test_segment_out_of_order_fails():
    with pytest.raises(ValidationError):
        SegmentSpec(
            train=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
            valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
            test=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        )


def test_research_spec_fit_defaults():
    spec = ResearchDatasetSpec(dataset_ref="cn_stock_daily@v1", segments=_ok_segments())
    assert spec.resolved_fit_start() == date(2024, 1, 1)
    assert spec.resolved_fit_end() == date(2024, 2, 29)
