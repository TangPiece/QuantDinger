"""Phase 6I：运行模式门禁（禁止 LIVE / 真实资金）。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import E2EMode, ENGINE_VERSION

_FORBIDDEN_ENV = frozenset({"LIVE", "FUNDED", "REAL_MONEY", "REAL"})
_FORBIDDEN_FRAGMENTS = ("live_trading", "real_money", "funded_account")


class E2EModeError(ValueError):
    """非法 E2E 模式或环境。"""


def assert_mode(mode: str | E2EMode, *, context: str = "") -> E2EMode:
    """校验模式为 PAPER / SHADOW / PAPER_REAL_MD。"""
    m = str(mode or "").upper()
    if m == "LIVE" or m in _FORBIDDEN_ENV:
        raise E2EModeError(f"LIVE/funded not allowed in Phase 6I ({context})")
    if m not in ("PAPER", "SHADOW", "PAPER_REAL_MD"):
        raise E2EModeError(f"invalid E2E mode {mode!r}")
    return m  # type: ignore[return-value]


def assert_environment(env: str, *, context: str = "") -> str:
    """OMS/Broker environment 不得为 LIVE。"""
    e = str(env or "").upper()
    if e in _FORBIDDEN_ENV:
        raise E2EModeError(f"environment {env!r} forbidden in 6I ({context})")
    return e


def assert_config_safe(config: Mapping[str, Any] | None) -> None:
    """扫描配置中的 LIVE / funded 关键字。"""
    if not config:
        return
    blob = str(config).lower()
    for frag in _FORBIDDEN_FRAGMENTS:
        if frag in blob:
            raise E2EModeError(f"config contains forbidden fragment {frag!r}")


def oms_environment_for_mode(mode: E2EMode | str) -> str:
    """PAPER 同步 submit（Simulated/Paper 注入）；SHADOW 不发单。"""
    m = assert_mode(mode)
    if m == "SHADOW":
        return "SHADOW"
    # PAPER / PAPER_REAL_MD：同步成交，避免 outbox 未 drain 导致 SUBMITTED 悬挂
    return "PAPER"


__all__ = [
    "ENGINE_VERSION",
    "E2EModeError",
    "assert_config_safe",
    "assert_environment",
    "assert_mode",
    "oms_environment_for_mode",
]
