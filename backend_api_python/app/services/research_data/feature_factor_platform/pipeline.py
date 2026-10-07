"""Factor Pipeline 元数据（winsorize / normalize / neutralize / direction）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class FactorPipelineSpec(BaseModel):
    """写入 FeatureDefinition.definition['factor_pipeline']。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    winsorize: Optional[dict[str, Any]] = None
    normalize: Optional[dict[str, Any]] = None
    neutralize: Optional[dict[str, Any]] = None
    direction: Literal["long", "short", "both"] = "long"

    def validate_fields(self) -> list[str]:
        reasons: list[str] = []
        for name, block in (
            ("winsorize", self.winsorize),
            ("normalize", self.normalize),
            ("neutralize", self.neutralize),
        ):
            if block is None:
                continue
            if not isinstance(block, dict):
                reasons.append(f"invalid_{name}_type")
                continue
            method = str(block.get("method") or "").strip()
            if not method:
                reasons.append(f"empty_{name}_method")
        if self.direction not in ("long", "short", "both"):
            reasons.append("invalid_direction")
        return reasons


PIPELINE_DEF_KEY = "factor_pipeline"


def merge_pipeline_into_definition(
    definition: dict[str, Any] | None,
    pipeline: FactorPipelineSpec | None,
) -> dict[str, Any]:
    sidecar = dict(definition or {})
    if pipeline is not None:
        sidecar[PIPELINE_DEF_KEY] = pipeline.model_dump(mode="json", exclude_none=True)
    return sidecar


__all__ = [
    "PIPELINE_DEF_KEY",
    "FactorPipelineSpec",
    "merge_pipeline_into_definition",
]
