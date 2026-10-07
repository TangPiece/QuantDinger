"""Phase 7C：从环境变量加载 Controlled Live 爆炸半径。"""

from __future__ import annotations

import os

from .protocol import ControlledLiveConfig


def _parse_csv(name: str, default: str) -> tuple[str, ...]:
    raw = (os.environ.get(name) or default).strip()
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    return tuple(parts)


def _parse_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return float(raw)


def _parse_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return int(raw)


def load_controlled_live_config() -> ControlledLiveConfig:
    """读取 CONTROLLED_LIVE_* 限制；CI 默认保守值。"""
    return ControlledLiveConfig(
        max_orders=_parse_int("CONTROLLED_LIVE_MAX_ORDERS", 1),
        max_quantity=_parse_float("CONTROLLED_LIVE_MAX_QUANTITY", 10.0),
        max_notional=_parse_float("CONTROLLED_LIVE_MAX_NOTIONAL", 5000.0),
        allowed_symbols=_parse_csv("CONTROLLED_LIVE_ALLOWED_SYMBOLS", "AAPL"),
        allowed_sides=_parse_csv("CONTROLLED_LIVE_ALLOWED_SIDES", "BUY"),
        allowed_order_types=_parse_csv("CONTROLLED_LIVE_ALLOWED_ORDER_TYPES", "LIMIT"),
    )


def allow_real_submit() -> bool:
    """真实 Alpaca POST 需显式 opt-in + 凭证（由 adapter 再校验）。"""
    v = (os.environ.get("CONTROLLED_LIVE_ALLOW_REAL_SUBMIT") or "").strip().lower()
    return v in ("true", "1", "yes", "on")
