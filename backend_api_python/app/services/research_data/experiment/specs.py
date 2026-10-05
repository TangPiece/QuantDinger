"""ExperimentSpec：顶层研究运行规格。"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.research_data.model_training.specs import ModelTrainSpec
from app.services.research_data.signal.specs import SignalRunSpec


@dataclass
class ExperimentSpec:
    """一次完整研究实验：训练 + 信号策略。"""

    name: str
    train: ModelTrainSpec
    signal: SignalRunSpec
    seed: int | None = None  # None 时使用 train.seed

    def resolved_seed(self) -> int:
        return int(self.seed if self.seed is not None else self.train.seed)
