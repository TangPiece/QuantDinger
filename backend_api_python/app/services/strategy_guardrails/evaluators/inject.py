"""Phase 8G：Fake inject 段解析（CI / verify）。"""

from __future__ import annotations

from typing import Any, Mapping

from ..protocol import BreachSignal, LifecyclePhase


def merge_guardrail_inject(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    if "guardrails" in raw and isinstance(raw["guardrails"], dict):
        return dict(raw["guardrails"])
    return dict(raw)


def breaches_from_inject(section: Mapping[str, Any] | None) -> list[BreachSignal]:
    if not section:
        return []
    raw_list = section.get("breaches") or section.get("signals") or []
    out: list[BreachSignal] = []
    for item in raw_list:
        if isinstance(item, BreachSignal):
            out.append(item)
        elif isinstance(item, dict):
            out.append(BreachSignal.model_validate(item))
    return out


def lifecycle_from_inject(section: Mapping[str, Any] | None) -> LifecyclePhase:
    if not section:
        return "UNKNOWN"
    phase = str(section.get("lifecycle_phase") or section.get("lifecycle") or "UNKNOWN").upper()
    if phase in ("SHADOW", "CONTROLLED_LIVE", "LIVE", "RETIRED", "UNKNOWN"):
        return phase  # type: ignore[return-value]
    return "UNKNOWN"


def recovery_healthy_from_inject(section: Mapping[str, Any] | None) -> bool | None:
    if not section:
        return None
    if "recovery_healthy" in section:
        return bool(section["recovery_healthy"])
    if "recovery_check_passed" in section:
        return bool(section["recovery_check_passed"])
    return None


__all__ = [
    "breaches_from_inject",
    "lifecycle_from_inject",
    "merge_guardrail_inject",
    "recovery_healthy_from_inject",
]
