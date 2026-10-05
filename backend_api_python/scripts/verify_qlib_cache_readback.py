#!/usr/bin/env python3
"""兼容入口：转发到 Phase 1D 一致性验收脚本。

完整六项验收请使用::

    python scripts/verify_phase1d_consistency.py
"""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "verify_phase1d_consistency.py"
    runpy.run_path(str(target), run_name="__main__")
