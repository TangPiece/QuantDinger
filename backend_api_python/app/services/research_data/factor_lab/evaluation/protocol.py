"""Phase 4C：Evaluation Domain 契约（无 IC；无 qlib/R2 SDK 类型）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.services.research_data.contracts import PricePolicy, _ContractModel

EVALUATOR_VERSION = "qd_factor_eval@1"
CALENDAR_VERSION = "derived_from_market@1"
SCHEMA_EVALUATION = "evaluation_panel@1"

SampleStatus = Literal[
    "VALID",
    "MISSING_FACTOR",
    "MISSING_RETURN",
    "SUSPENDED",
    "OUT_OF_UNIVERSE",
    "PRICE_INVALID",
    "PIT_INVALID",
]

EvaluationMode = Literal["CROSS_SECTIONAL", "TIME_SERIES"]

ReturnDefinition = Literal[
    "close_to_close",
    "close_to_next_open",
    "next_open_to_close",
    "open_to_open",
]


class ReturnSpec(_ContractModel):
    """远期收益定义；horizon 由 Spec 驱动，禁止引擎硬编码。"""

    definition: ReturnDefinition = "next_open_to_close"
    horizons: list[int] = Field(default_factory=lambda: [1, 5])
    execution_delay: int = 1
    entry_price: Literal["open", "close"] = "open"
    exit_price: Literal["open", "close"] = "close"

    @field_validator("horizons")
    @classmethod
    def _horizons_positive(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("horizons must be non-empty")
        out = sorted({int(h) for h in v})
        if any(h <= 0 for h in out):
            raise ValueError("horizons must be positive trading-day counts")
        return out

    @field_validator("execution_delay")
    @classmethod
    def _delay_nonneg(cls, v: int) -> int:
        if int(v) < 0:
            raise ValueError("execution_delay must be >= 0")
        return int(v)

    @model_validator(mode="after")
    def _align_prices(self) -> "ReturnSpec":
        """按 definition 校正默认 entry/exit 价格字段。"""
        mapping = {
            "close_to_close": ("close", "close"),
            "close_to_next_open": ("close", "open"),
            "next_open_to_close": ("open", "close"),
            "open_to_open": ("open", "open"),
        }
        ep, xp = mapping[self.definition]
        # 允许显式覆盖，但默认与 definition 对齐
        object.__setattr__(self, "entry_price", self.entry_price or ep)
        object.__setattr__(self, "exit_price", self.exit_price or xp)
        if self.definition == "next_open_to_close":
            object.__setattr__(self, "entry_price", "open")
            object.__setattr__(self, "exit_price", "close")
        elif self.definition == "close_to_close":
            object.__setattr__(self, "entry_price", "close")
            object.__setattr__(self, "exit_price", "close")
        elif self.definition == "open_to_open":
            object.__setattr__(self, "entry_price", "open")
            object.__setattr__(self, "exit_price", "open")
        elif self.definition == "close_to_next_open":
            object.__setattr__(self, "entry_price", "close")
            object.__setattr__(self, "exit_price", "open")
        return self


class MissingDataPolicy(_ContractModel):
    """缺失策略：默认保留行，仅标记 sample_status。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        populate_by_name=True,
    )

    factor: Literal["drop", "keep_status"] = "keep_status"
    return_: Literal["drop", "keep_status"] = Field(
        default="keep_status", alias="return"
    )


class EvaluationSpec(_ContractModel):
    """因子评价规格：钉住 FactorDataset + Universe Snapshot + Return。"""

    factor_dataset_id: str
    universe_code: str
    snapshot_id: str
    start_date: str
    end_date: str
    universe_version: Optional[str] = None
    frequency: str = "1d"
    return_spec: ReturnSpec = Field(default_factory=ReturnSpec)
    price_policy: PricePolicy = Field(default_factory=PricePolicy)
    missing_data_policy: MissingDataPolicy = Field(default_factory=MissingDataPolicy)
    # 统计层过滤白名单；4C 只写入 status，不按此 drop（除非 policy=drop）
    sample_policy: list[SampleStatus] = Field(
        default_factory=lambda: ["VALID"]
    )
    mode: EvaluationMode = "CROSS_SECTIONAL"
    evaluator_version: str = EVALUATOR_VERSION
    calendar_version: str = CALENDAR_VERSION
    exchange: str = "CN"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationPlan(_ContractModel):
    """不可变评价计划（hash 输入的规范化视图）。"""

    evaluation_hash: str
    factor_dataset_id: str
    factor_dataset_hash: str
    factor_ref: str = ""
    snapshot_id: str
    universe_code: str
    universe_version: str = ""
    start_date: str
    end_date: str
    frequency: str = "1d"
    return_spec: ReturnSpec
    price_policy: PricePolicy = Field(default_factory=PricePolicy)
    mode: EvaluationMode = "CROSS_SECTIONAL"
    evaluator_version: str = EVALUATOR_VERSION
    calendar_version: str = CALENDAR_VERSION
    exchange: str = "CN"
    schema_version: str = SCHEMA_EVALUATION
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationFrame(_ContractModel):
    """评价面板内存出口（writer 前转 Arrow）。"""

    records: list[dict[str, Any]] = Field(default_factory=list)
    horizons: list[int] = Field(default_factory=list)
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    row_count: int = 0
    mode: EvaluationMode = "CROSS_SECTIONAL"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_records(
        cls,
        records: list[dict[str, Any]],
        *,
        horizons: list[int],
        mode: EvaluationMode = "CROSS_SECTIONAL",
    ) -> "EvaluationFrame":
        """从行字典构造并填充日期范围。"""
        dates: list[str] = []
        for r in records:
            d = r.get("factor_date")
            if d is None:
                continue
            if isinstance(d, date) and not isinstance(d, datetime):
                dates.append(d.isoformat())
            else:
                dates.append(str(d)[:10])
        return cls(
            records=records,
            horizons=list(horizons),
            min_date=min(dates) if dates else None,
            max_date=max(dates) if dates else None,
            row_count=len(records),
            mode=mode,
        )


class EvaluationManifest(_ContractModel):
    """R2 Evaluation Manifest。"""

    evaluation_hash: str
    factor_dataset_id: str
    factor_dataset_hash: str
    evaluation_spec: dict[str, Any] = Field(default_factory=dict)
    return_spec: dict[str, Any] = Field(default_factory=dict)
    universe_code: str = ""
    universe_version: str = ""
    snapshot_id: str = ""
    row_count: int = 0
    min_date: str = ""
    max_date: str = ""
    checksum: str = ""
    evaluator_version: str = EVALUATOR_VERSION
    schema_version: str = SCHEMA_EVALUATION
    mode: EvaluationMode = "CROSS_SECTIONAL"
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
