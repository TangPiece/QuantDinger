"""L4 Signal Diff。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .loaders import normalize_instrument
from .protocol import LayerResult


def _index_scores(
    rows: Sequence[Mapping[str, Any]], *, value_key: str
) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for r in rows:
        dt = str(r.get("datetime") or r.get("trading_date") or "")[:10]
        inst = normalize_instrument(
            str(r.get("instrument") or r.get("instrument_key") or "")
        )
        if not dt or not inst:
            continue
        raw = r.get(value_key, r.get("score", r.get("value")))
        if raw is None:
            continue
        try:
            out[(dt, inst)] = float(raw)
        except (TypeError, ValueError):
            continue
    return out


def diff_signal(
    qd_rows: Sequence[Mapping[str, Any]],
    qlib_rows: Sequence[Mapping[str, Any]],
    *,
    abs_tol: float = 1e-8,
) -> LayerResult:
    """比较 score 面板（NUMERIC）。"""
    a = _index_scores(qd_rows, value_key="score")
    b = _index_scores(qlib_rows, value_key="score")
    common = sorted(set(a) & set(b))
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    max_abs = 0.0
    first = ""
    for key in common:
        d = abs(a[key] - b[key])
        if d > max_abs:
            max_abs = d
            if d > abs_tol and not first:
                first = f"{key[0]}|{key[1]} abs={d}"
    details: dict[str, Any] = {
        "n_qd": len(a),
        "n_qlib": len(b),
        "n_common": len(common),
        "n_only_qd": len(only_a),
        "n_only_qlib": len(only_b),
    }
    # 允许一侧为空（未产出 prediction）时 SKIP→FAIL 偏严；要求两侧都有
    if not a and not b:
        return LayerResult(
            layer="signal",
            kind="NUMERIC",
            status="PASS",
            message="both empty",
            details=details,
        )
    if only_a or only_b or max_abs > abs_tol:
        return LayerResult(
            layer="signal",
            kind="NUMERIC",
            status="FAIL",
            message="signal mismatch",
            max_abs_diff=max_abs,
            first_divergence=first or (only_a[0][0] if only_a else ""),
            details=details,
        )
    return LayerResult(
        layer="signal",
        kind="NUMERIC",
        status="PASS",
        message="signals aligned",
        max_abs_diff=max_abs,
        details=details,
    )
