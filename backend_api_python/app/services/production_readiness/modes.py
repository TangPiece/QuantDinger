"""Phase 6J：模式门禁 — 禁止 LIVE / 真实资金。"""

from __future__ import annotations

from typing import Literal

ReadinessMode = Literal["PAPER", "SANDBOX"]


class ReadinessModeError(RuntimeError):
    """非法模式。"""


def assert_mode(mode: str) -> ReadinessMode:
    m = str(mode or "PAPER").strip().upper()
    if m == "LIVE":
        raise ReadinessModeError("LIVE forbidden in Phase 6J")
    if m not in ("PAPER", "SANDBOX"):
        raise ReadinessModeError(f"unsupported readiness mode: {mode!r}")
    return m  # type: ignore[return-value]
