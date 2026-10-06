"""L3 Universe Diff。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .loaders import normalize_instrument
from .protocol import LayerResult


def diff_universe(
    qd_id: Mapping[str, Any],
    qlib_id: Mapping[str, Any],
    *,
    qd_membership: Sequence[str] | Mapping[str, Sequence[str]] | None = None,
    qlib_membership: Sequence[str] | Mapping[str, Sequence[str]] | None = None,
) -> LayerResult:
    """同一 snapshot_id；membership 集合 EXACT。"""
    details: dict[str, Any] = {
        "qd_universe": qd_id.get("universe_code"),
        "qd_snapshot": qd_id.get("snapshot_id"),
        "qlib_universe": qlib_id.get("universe_code"),
        "qlib_snapshot": qlib_id.get("snapshot_id"),
    }
    mismatches: list[str] = []

    qd_snap = str(qd_id.get("snapshot_id") or "")
    ql_snap = str(qlib_id.get("snapshot_id") or "")
    if qd_snap and ql_snap and qd_snap != ql_snap:
        mismatches.append(f"snapshot_id {qd_snap}!={ql_snap}")
    elif not qd_snap and not ql_snap:
        # 注入场景：两侧都空则用默认注入 id 视为对齐
        details["note"] = "both snapshot_id empty; treated as shared injected snapshot"
    elif qd_snap != ql_snap:
        # 一侧有一侧无：要求一致身份来自同一 strategy
        if qd_snap and not ql_snap:
            details["inferred_qlib_snapshot"] = qd_snap
        elif ql_snap and not qd_snap:
            details["inferred_qd_snapshot"] = ql_snap

    qd_u = str(qd_id.get("universe_code") or "")
    ql_u = str(qlib_id.get("universe_code") or "")
    if qd_u and ql_u and qd_u != ql_u:
        mismatches.append(f"universe_code {qd_u}!={ql_u}")

    def _flat(m) -> set[str]:
        if m is None:
            return set()
        if isinstance(m, Mapping):
            out: set[str] = set()
            for vals in m.values():
                for x in vals:
                    out.add(normalize_instrument(str(x)))
            return out
        return {normalize_instrument(str(x)) for x in m}

    a = _flat(qd_membership)
    b = _flat(qlib_membership)
    if a or b:
        details["qd_n"] = len(a)
        details["qlib_n"] = len(b)
        if a != b:
            mismatches.append(
                f"membership mismatch only_qd={sorted(a - b)[:5]} "
                f"only_qlib={sorted(b - a)[:5]}"
            )

    if mismatches:
        return LayerResult(
            layer="universe",
            kind="EXACT",
            status="FAIL",
            message="; ".join(mismatches),
            details=details,
        )
    return LayerResult(
        layer="universe",
        kind="EXACT",
        status="PASS",
        message="universe snapshot aligned",
        details=details,
    )
