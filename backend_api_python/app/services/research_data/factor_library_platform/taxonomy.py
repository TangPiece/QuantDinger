"""Factor category 规范化。"""

from __future__ import annotations

from .protocol import FactorCategory

_ALIASES: dict[str, FactorCategory] = {
    "momentum": "MOMENTUM",
    "value": "VALUE",
    "quality": "QUALITY",
    "volatility": "VOLATILITY",
    "liquidity": "LIQUIDITY",
    "sentiment": "SENTIMENT",
    "technical": "TECHNICAL",
    "other": "OTHER",
}


def normalize_category(raw: str) -> FactorCategory:
    key = str(raw or "").strip().lower()
    if not key:
        return "OTHER"
    if key.upper() in _ALIASES.values():
        return key.upper()  # type: ignore[return-value]
    return _ALIASES.get(key, "OTHER")


def normalize_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in tags or []:
        s = str(t).strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return sorted(out)


__all__ = ["normalize_category", "normalize_tags"]
