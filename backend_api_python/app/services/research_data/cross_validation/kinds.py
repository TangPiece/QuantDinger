"""DiffKind：每层差异分类。"""

from __future__ import annotations

from typing import Literal

DiffKind = Literal[
    "EXACT",
    "NUMERIC",
    "SEMANTIC",
    "EXPECTED_DIFFERENCE",
    "UNSUPPORTED",
]

LayerName = Literal[
    "dataset",
    "pit",
    "universe",
    "signal",
    "portfolio",
    "execution",
    "nav",
    "performance",
]

CvStatus = Literal["PASSED", "FAILED", "PASSED_WITH_EXPECTED_DIFF"]

# 默认层 → DiffKind（GROSS baseline）
DEFAULT_LAYER_KINDS: dict[str, DiffKind] = {
    "dataset": "EXACT",
    "pit": "EXACT",
    "universe": "EXACT",
    "signal": "NUMERIC",
    "portfolio": "NUMERIC",
    "execution": "SEMANTIC",
    "nav": "NUMERIC",
    "performance": "NUMERIC",
}
