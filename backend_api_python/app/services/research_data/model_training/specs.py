"""ModelTrainSpec：训练运行时规格（不进 Domain DatasetDefinition）。"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.services.research_data.contracts import ModelDefinition
from app.services.research_data.qlib_adapter.specs import ResearchDatasetSpec


def default_lgb_config() -> dict[str, Any]:
    """Fixture 友好：少轮次 + 固定 seed 参数位。"""
    return {
        "loss": "mse",
        "num_boost_round": 8,
        "early_stopping_rounds": 3,
        "learning_rate": 0.05,
        "num_leaves": 8,
        "seed": 42,
    }


def builtin_lgb_baseline_model() -> ModelDefinition:
    """默认 LightGBM 基线模型资产。"""
    return ModelDefinition(
        code="lgb_baseline",
        version="1",
        name="LightGBM baseline",
        engine="lightgbm",
        config=default_lgb_config(),
    )


class ModelTrainSpec(BaseModel):
    """一次训练：Dataset spec + 模型 ref 或内联 ModelDefinition。"""

    model_config = ConfigDict(extra="forbid")

    dataset_spec: ResearchDatasetSpec
    model: Optional[ModelDefinition] = None
    model_ref: Optional[str] = None
    seed: int = 42
    experiment_name: str = "phase2d_train"
    config_override: dict[str, Any] = Field(default_factory=dict)

    def resolved_model_ref(self, model: ModelDefinition) -> str:
        return f"{model.code}@{model.version}"
