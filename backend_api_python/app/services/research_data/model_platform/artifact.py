"""ModelArtifact 索引组装（非 bin 本体）。"""

from __future__ import annotations

from .pin import pin_model_artifact
from .protocol import ModelArtifact, ModelArtifactSpec

__all__ = ["ModelArtifact", "ModelArtifactSpec", "pin_model_artifact"]
