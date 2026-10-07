"""Model type / tag 规范化。"""

from __future__ import annotations

from .protocol import ModelType

_ALIASES: dict[str, ModelType] = {
    "regression": "REGRESSION",
    "classification": "CLASSIFICATION",
    "ranking": "RANKING",
    "time_series": "TIME_SERIES",
    "timeseries": "TIME_SERIES",
    "deep_learning": "DEEP_LEARNING",
    "deeplearning": "DEEP_LEARNING",
    "ensemble": "ENSEMBLE",
    "custom": "CUSTOM",
}


def normalize_model_type(raw: str) -> ModelType:
    key = str(raw or "").strip()
    if not key:
        return "CUSTOM"
    upper = key.upper()
    if upper in (
        "REGRESSION",
        "CLASSIFICATION",
        "RANKING",
        "TIME_SERIES",
        "DEEP_LEARNING",
        "ENSEMBLE",
        "CUSTOM",
    ):
        return upper  # type: ignore[return-value]
    return _ALIASES.get(key.lower(), "CUSTOM")


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


__all__ = ["normalize_model_type", "normalize_tags"]
