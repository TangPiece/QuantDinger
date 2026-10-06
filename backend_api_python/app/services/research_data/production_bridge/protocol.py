"""Phase 5F：Production Bridge Domain（不暴露 Broker / qlib）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import Field, field_validator

from app.services.research_data.contracts import (
    OrderIntent,
    ProductionBundleSummary,
    ProductionDeploymentRunSummary,
    ProductionDeploymentSummary,
    Signal,
    TargetPosition,
    _ContractModel,
)

ENGINE_VERSION = "qd_production_bridge@1"

BundleStatus = Literal[
    "DRAFT",
    "VALIDATED",
    "CANDIDATE",
    "APPROVED",
    "DEPLOYED",
    "PAUSED",
    "RETIRED",
]

DeploymentStatus = Literal["DEPLOYED", "PAUSED", "RETIRED"]


class DependencyLock(_ContractModel):
    """运行时依赖锁定。"""

    python_version: str = ""
    engine_versions: dict[str, str] = Field(default_factory=dict)
    adapter_versions: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class ProductionBundleSpec(_ContractModel):
    """冻结输入规格。"""

    strategy_hash: str
    cv_hash: str
    strategy_code: str = ""
    backtest_hash: str = ""
    qlib_run_hash: str = ""
    dataset_hash: str = ""
    materialization_id: str = ""
    feature_hashes: list[str] = Field(default_factory=list)
    processor_hash: str = ""
    processor_artifact_uri: str = ""
    pipeline_digest: str = ""
    model_artifact_id: str = ""
    model_version: str = ""
    universe_code: str = ""
    snapshot_id: str = ""
    execution_policy: str = "NEXT_OPEN"
    realism: str = "GROSS"
    market_rule: str = "CN_A"
    parent_bundle_hash: str = ""
    dependency_lock: DependencyLock = Field(default_factory=DependencyLock)
    bundle_engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("strategy_hash", "cv_hash")
    @classmethod
    def _req(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("strategy_hash and cv_hash required")
        return s


class BundleManifest(_ContractModel):
    """Bundle 产物清单。"""

    bundle_hash: str
    strategy_hash: str = ""
    engine_version: str = ENGINE_VERSION
    checksum: str = ""
    storage_uri: str = ""
    file_checksums: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GateResult(_ContractModel):
    """单门禁结果。"""

    gate: str
    passed: bool = True
    severity: Literal["P0", "P1", "P2"] = "P0"
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class FeatureParityReport(_ContractModel):
    """Offline vs Online Feature 对齐报告。"""

    n_compared: int = 0
    max_abs_diff: float = 0.0
    max_rel_diff: float = 0.0
    passed: bool = True
    abs_tol: float = 1e-8
    rel_tol: float = 1e-6
    first_divergence: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class InferenceRequest(_ContractModel):
    """生产推理请求（干跑）。"""

    bundle_hash: str
    trading_date: date
    knowledge_time: Optional[datetime] = None
    instruments: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InferenceResponse(_ContractModel):
    """生产推理响应；停在 OrderIntent。"""

    run_id: str
    bundle_hash: str
    trading_date: str
    status: Literal["OK", "STOPPED", "FAILED"] = "OK"
    signals: list[Signal] = Field(default_factory=list)
    targets: list[TargetPosition] = Field(default_factory=list)
    order_intents: list[OrderIntent] = Field(default_factory=list)
    gate_results: list[GateResult] = Field(default_factory=list)
    feature_version: str = ""
    model_version: str = ""
    strategy_version: str = ""
    inference_timestamp: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "BundleManifest",
    "BundleStatus",
    "DependencyLock",
    "DeploymentStatus",
    "FeatureParityReport",
    "GateResult",
    "InferenceRequest",
    "InferenceResponse",
    "ProductionBundleSpec",
    "ProductionBundleSummary",
    "ProductionDeploymentRunSummary",
    "ProductionDeploymentSummary",
]
