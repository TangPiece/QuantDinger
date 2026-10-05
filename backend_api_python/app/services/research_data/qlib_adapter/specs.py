"""Phase 2B 运行时规格：Segment / ResearchDatasetSpec（不进 Domain DatasetDefinition）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from app.services.research_data.contracts import LabelDefinition


class SegmentRange(BaseModel):
    """单个时间段 [start, end]（含端点）。"""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> "SegmentRange":
        if self.start > self.end:
            raise ValueError(f"segment start > end: {self.start} > {self.end}")
        return self

    def as_tuple(self) -> tuple[str, str]:
        return self.start.isoformat(), self.end.isoformat()


class SegmentSpec(BaseModel):
    """train / valid / test 时间切分；必须严格时间有序、无重叠。"""

    model_config = ConfigDict(extra="forbid")

    train: SegmentRange
    valid: SegmentRange
    test: SegmentRange

    @model_validator(mode="after")
    def _no_leakage_order(self) -> "SegmentSpec":
        # Train < Valid < Test（相邻允许：train.end < valid.start）
        if not (self.train.end < self.valid.start):
            raise ValueError(
                f"train must end before valid starts: "
                f"train.end={self.train.end} valid.start={self.valid.start}"
            )
        if not (self.valid.end < self.test.start):
            raise ValueError(
                f"valid must end before test starts: "
                f"valid.end={self.valid.end} test.start={self.test.start}"
            )
        return self

    def handler_window(self) -> tuple[date, date]:
        """Handler 加载窗口：train.start .. test.end。"""
        return self.train.start, self.test.end

    def to_qlib_segments(self) -> dict[str, tuple[str, str]]:
        return {
            "train": self.train.as_tuple(),
            "valid": self.valid.as_tuple(),
            "test": self.test.as_tuple(),
        }

    def canonical_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ResearchDatasetSpec(BaseModel):
    """一次研究 Dataset 构建规格（segments/label 运行时绑定）。"""

    model_config = ConfigDict(extra="forbid")

    dataset_ref: str
    segments: SegmentSpec
    label: Optional[LabelDefinition] = None
    fit_start: Optional[date] = None
    fit_end: Optional[date] = None
    force_materialize: bool = False

    def resolved_fit_start(self) -> date:
        return self.fit_start or self.segments.train.start

    def resolved_fit_end(self) -> date:
        return self.fit_end or self.segments.train.end

    @model_validator(mode="after")
    def _fit_ordered(self) -> "ResearchDatasetSpec":
        fs = self.fit_start or self.segments.train.start
        fe = self.fit_end or self.segments.train.end
        if fs > fe:
            raise ValueError("fit_start > fit_end")
        return self


def default_fwd_ret_label(*, horizon: int = 5) -> LabelDefinition:
    """默认未来 N 日收益 Label。"""
    return LabelDefinition(
        code="fwd_ret",
        version="1",
        name=f"Forward {horizon}d return",
        expression=f"Ref($close, -{horizon}) / $close - 1",
        horizon=horizon,
    )
