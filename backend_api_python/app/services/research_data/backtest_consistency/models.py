"""Phase 3E Consistency 契约模型（无 qlib 类型）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

ConsistencyStatus = Literal["PASSED", "FAILED", "SKIPPED_QLIB"]
ConsistencyLevel = Literal["L0", "L1", "L2", "L3", "L4", "L5"]
DiffDimension = Literal[
    "equity",
    "position",
    "trade",
    "cost",
    "cash",
    "rejected",
    "signal",
]
AttributionComponent = Literal[
    "commission",
    "slippage",
    "t_plus",
    "lot",
    "limit",
    "suspend",
    "cash",
    "other",
]


class ConsistencyScenario(_ContractModel):
    """Golden / 分层场景描述。"""

    scenario_id: str
    level: ConsistencyLevel
    description: str = ""
    instrument_keys: list[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""


class ConsistencyDiff(_ContractModel):
    """逐日/逐标的差异行。"""

    dimension: DiffDimension
    instrument: Optional[str] = None
    trading_date: Optional[str] = None
    qlib_value: Optional[float] = None
    quantdinger_value: Optional[float] = None
    absolute_diff: Optional[float] = None
    relative_diff: Optional[float] = None
    reason: Optional[str] = None


class ConsistencyAttribution(_ContractModel):
    """分层归因项：对收益差的贡献（相对初始资金）。"""

    component: AttributionComponent
    return_impact: float = 0.0
    notes: str = ""


class ConsistencyReport(_ContractModel):
    """双引擎一致性报告。"""

    run_id: str
    dataset_hash: str
    signal_artifact_id: Optional[str] = None
    semantic_fingerprint: str = ""
    level: ConsistencyLevel = "L0"
    qlib_result_id: Optional[str] = None
    qd_result_id: Optional[str] = None
    diffs: list[ConsistencyDiff] = Field(default_factory=list)
    attribution: list[ConsistencyAttribution] = Field(default_factory=list)
    max_equity_diff: float = 0.0
    max_position_diff: float = 0.0
    status: ConsistencyStatus = "PASSED"
    engine_version: str = ""
    artifact_uris: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
