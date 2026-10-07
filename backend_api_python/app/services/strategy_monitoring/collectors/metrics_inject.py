"""Phase 8F：Fake inject 分段解析（CI / verify）。"""

from __future__ import annotations

from typing import Any, Mapping


def merge_inject_sections(inject: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """支持嵌套 {performance:{...}} 或扁平键 performance_*。"""
    data = dict(inject or {})
    sections: dict[str, dict[str, Any]] = {
        "performance": {},
        "risk": {},
        "execution": {},
        "signal": {},
        "portfolio": {},
        "market_data": {},
        "reconciliation": {},
        "capacity": {},
    }
    for key, val in data.items():
        if isinstance(val, dict) and key in sections:
            sections[key] = dict(val)
            continue
        for prefix in sections:
            p = f"{prefix}_"
            if str(key).startswith(p):
                sections[prefix][str(key)[len(p) :]] = val
    # 顶层标量归入 performance（兼容简单 inject）
    scalar_keys = {
        "shadow_drift",
        "max_drawdown",
        "sharpe",
        "return_total",
        "reject_rate",
        "signal_correlation",
    }
    for k in scalar_keys:
        if k in data and k not in sections["performance"]:
            sections["performance"][k] = data[k]
    return sections


__all__ = ["merge_inject_sections"]
