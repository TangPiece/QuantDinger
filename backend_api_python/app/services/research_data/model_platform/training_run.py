"""TrainingRun 组装（仅 pin，不执行训练）。"""

from __future__ import annotations

from .pin import pin_training_run
from .protocol import TrainingRun, TrainingRunSpec

__all__ = ["TrainingRun", "TrainingRunSpec", "pin_training_run"]
