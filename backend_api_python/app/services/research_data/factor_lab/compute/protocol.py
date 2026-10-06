"""Factor Compute 契约：Engine Protocol / Plan / PIT Context / Frame。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional, Protocol, runtime_checkable

from pydantic import Field

from app.services.research_data.contracts import PricePolicy, _ContractModel


class PITComputeContext(_ContractModel):
    """PIT / 计算窗口上下文；fundamental 必须遵守 available_time <= knowledge_time。"""

    knowledge_time: datetime
    snapshot_id: str
    start_date: str
    end_date: str
    exchange: str = "CN"
    universe_code: str = ""
    universe_version: Optional[str] = None
    price_policy: PricePolicy = Field(default_factory=PricePolicy)
    # 输入数据钉住（可选）；参与 result dataset_hash
    canonical_dataset_hash: Optional[str] = None
    processor_ref: Optional[str] = None


class ComputePlan(_ContractModel):
    """不可变计算计划（不含引擎运行时状态）。"""

    factor_ref: str
    factor_hash: str
    plan_hash: str
    snapshot_id: str
    dataset_hash: str  # 输入钉住 / result hash 输入之一
    engine: Literal["qlib", "quantdinger", "duckdb", "polars", "level2"]
    engine_version: str = ""
    dependency_order: list[str] = Field(default_factory=list)
    frequency: str = "1d"
    universe_code: str = ""
    start_date: str = ""
    end_date: str = ""
    knowledge_time: datetime
    price_policy: PricePolicy = Field(default_factory=PricePolicy)
    processor_ref: Optional[str] = None
    layout: Literal["long", "wide"] = "long"
    schema_version: str = "factor_daily_long@1"
    expression: str = ""
    information_policy: str = "UNKNOWN"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorFrame(_ContractModel):
    """引擎输出的因子帧描述（数值在 records / 外部 DataFrame）。"""

    layout: Literal["long", "wide"] = "long"
    # long: list[{instrument_key, trading_date, value}]
    # wide: list[{instrument_key, trading_date, <factor cols>...}]
    records: list[dict[str, Any]] = Field(default_factory=list)
    factor_columns: list[str] = Field(default_factory=list)
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    row_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_records(
        cls,
        records: list[dict[str, Any]],
        *,
        layout: Literal["long", "wide"] = "long",
        factor_columns: list[str] | None = None,
    ) -> "FactorFrame":
        """从行字典构造，并填充日期范围。"""
        dates = []
        for r in records:
            d = r.get("trading_date")
            if d is None:
                continue
            if isinstance(d, date) and not isinstance(d, datetime):
                dates.append(d.isoformat())
            else:
                dates.append(str(d)[:10])
        return cls(
            layout=layout,
            records=records,
            factor_columns=list(factor_columns or []),
            min_date=min(dates) if dates else None,
            max_date=max(dates) if dates else None,
            row_count=len(records),
        )


@runtime_checkable
class FactorComputeEngine(Protocol):
    """统一因子计算引擎协议（无 qlib 类型泄漏到 Domain）。"""

    name: str

    def supports(self, factor, plan: ComputePlan) -> bool:
        """是否可执行该 plan。"""
        ...

    def compute(self, plan: ComputePlan, *, query, registry) -> FactorFrame:
        """执行计算，返回 FactorFrame。"""
        ...
