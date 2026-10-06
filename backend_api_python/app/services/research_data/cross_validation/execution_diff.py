"""L6 Execution Diff（timing / compatibility）。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import LayerResult


def diff_execution(
    qd_policy: Mapping[str, Any],
    qlib_policy: Mapping[str, Any],
    *,
    compatibility: Mapping[str, Any] | None = None,
    realism: str = "GROSS",
) -> LayerResult:
    """比较执行时点语义；NET 时标注 EXPECTED/UNSUPPORTED。"""
    details: dict[str, Any] = {
        "qd": dict(qd_policy),
        "qlib": dict(qlib_policy),
        "realism": realism,
    }
    qd_mode = str(qd_policy.get("mode") or qd_policy.get("execution_policy") or "")
    ql_mode = str(qlib_policy.get("mode") or qlib_policy.get("execution_policy") or "")
    qd_fill = str(qd_policy.get("fill_field") or qd_policy.get("fills_field") or "")
    ql_fill = str(qlib_policy.get("fill_field") or qlib_policy.get("fills_field") or "")

    mismatches: list[str] = []
    if qd_mode and ql_mode and qd_mode != ql_mode:
        mismatches.append(f"mode {qd_mode}!={ql_mode}")
    if qd_fill and ql_fill and qd_fill != ql_fill:
        mismatches.append(f"fill_field {qd_fill}!={ql_fill}")

    expected_notes: list[str] = []
    kind = "SEMANTIC"
    if realism == "NET" and compatibility:
        items = compatibility.get("items") or []
        for it in items:
            level = str(it.get("level") or "")
            cap = str(it.get("capability") or "")
            if level in ("PARTIAL", "UNSUPPORTED"):
                expected_notes.append(f"{cap}:{level}")
        if expected_notes:
            kind = "EXPECTED_DIFFERENCE"
            details["compatibility_flags"] = expected_notes

    if mismatches:
        return LayerResult(
            layer="execution",
            kind="SEMANTIC",
            status="FAIL",
            message="; ".join(mismatches),
            details=details,
        )

    msg = "execution timing aligned"
    if expected_notes:
        msg = "timing aligned; cost/T+1 expected differences noted"
    return LayerResult(
        layer="execution",
        kind=kind,  # type: ignore[arg-type]
        status="PASS",
        message=msg,
        details=details,
    )
