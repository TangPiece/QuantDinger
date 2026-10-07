"""Phase 8A：Strategy Registry 契约（身份 + 版本 + Policy 绑定 SSOT）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_strategy_registry@1"

VersionSource = Literal["RESEARCH", "BUNDLE", "MANUAL"]

StrategyStatus = Literal["ACTIVE", "PAUSED", "RETIRED"]


class _RegModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PolicyBindings(_RegModel):
    """风险与执行策略引用（注册后随版本钉扎，不可原地修改）。"""

    risk_policy_ref: str = ""
    execution_policy_ref: str = "NEXT_OPEN"


class StrategyRecord(_RegModel):
    """策略身份行；strategy_id ≡ normalize(strategy_code)。"""

    strategy_code: str
    display_name: str = ""
    owner: str = ""
    status: StrategyStatus = "ACTIVE"
    active_version: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyVersionRecord(_RegModel):
    """不可变版本钉扎：dataset/model/feature/bundle/policy 全量指纹。"""

    version_id: str
    strategy_code: str
    strategy_version: str
    dataset_hash: str = ""
    snapshot_id: str = ""
    model_version: str = ""
    model_artifact_id: str = ""
    feature_version: str = ""
    processor_version: str = ""
    processor_hash: str = ""
    strategy_hash: str = ""
    bundle_hash: str = ""
    risk_policy_ref: str = ""
    execution_policy_ref: str = "NEXT_OPEN"
    content_hash: str = ""
    registered_at: str = ""
    source: VersionSource = "MANUAL"
    storage_uri: str = ""
    immutable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "PolicyBindings",
    "StrategyRecord",
    "StrategyVersionRecord",
    "StrategyStatus",
    "VersionSource",
]
