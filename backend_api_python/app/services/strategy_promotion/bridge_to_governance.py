"""Phase 8D：编排 7E lifecycle / scale（无 auto LIVE）。"""

from __future__ import annotations

from typing import Any

from app.services.strategy_registry.identity import strategy_id_from_code


class GovernanceBridgeError(RuntimeError):
    pass


def _ensure_lifecycle(governance: Any, strategy_code: str, strategy_version: str) -> str:
    sid = strategy_id_from_code(strategy_code)
    if not hasattr(governance, "register_strategy_version"):
        return sid
    if sid not in getattr(governance, "_lifecycle", {}):
        governance.register_strategy_version(
            strategy_id=sid,
            strategy_version=strategy_version,
        )
    return sid


def apply_governance_for_target(
    governance: Any | None,
    *,
    strategy_code: str,
    strategy_version: str,
    to_environment: str,
    live_go_live_approved: bool = False,
) -> str:
    """按目标环境推进 lifecycle；LIVE 须显式审批 + L4。"""
    if governance is None:
        return ""
    sid = _ensure_lifecycle(governance, strategy_code, strategy_version)
    dst = str(to_environment).upper()
    lc = governance._lifecycle.get(sid)
    state = str(getattr(lc, "state", "DRAFT") or "DRAFT").upper()

    if dst == "SHADOW":
        if state == "DRAFT":
            governance.transition_lifecycle(sid, "VALIDATING")
            state = "VALIDATING"
        if state == "VALIDATING":
            governance.transition_lifecycle(sid, "SHADOW")
        return "SHADOW"

    if dst == "CONTROLLED_LIVE":
        if state not in ("SHADOW", "CONTROLLED_LIVE"):
            apply_governance_for_target(
                governance,
                strategy_code=strategy_code,
                strategy_version=strategy_version,
                to_environment="SHADOW",
            )
            state = "SHADOW"
        if state == "SHADOW":
            governance.transition_lifecycle(sid, "CONTROLLED_LIVE")
        st = getattr(governance, "_scale", {}).get(sid)
        if st is not None:
            governance._scale[sid] = st.model_copy(
                update={"current_level": "L1_CONTROLLED"}
            )
        return "CONTROLLED_LIVE"

    if dst == "LIVE":
        lc = governance._lifecycle.get(sid)
        scale = getattr(lc, "scale_level", "L0_SHADOW")
        if scale != "L4_PRODUCTION":
            st = getattr(governance, "_scale", {}).get(sid)
            if st is None:
                from app.services.trading_governance.protocol import ScaleState

                st = ScaleState(strategy_id=sid, current_level="L4_PRODUCTION")
            else:
                st = st.model_copy(update={"current_level": "L4_PRODUCTION"})
            governance._scale[sid] = st
            lc = lc.model_copy(update={"scale_level": "L4_PRODUCTION"}) if lc else lc
            if lc is not None:
                governance._lifecycle[sid] = lc
        governance.transition_lifecycle(
            sid,
            "LIVE",
            live_go_live_approved=live_go_live_approved,
        )
        return "LIVE"

    raise GovernanceBridgeError(f"unsupported governance target: {dst}")


__all__ = ["GovernanceBridgeError", "apply_governance_for_target"]
