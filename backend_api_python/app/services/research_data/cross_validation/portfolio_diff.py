"""L5 Portfolio / TargetPosition Diff。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .loaders import normalize_instrument
from .protocol import LayerResult


def _index_weights(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for r in rows:
        dt = str(r.get("datetime") or r.get("trading_date") or "")[:10]
        inst = normalize_instrument(
            str(r.get("instrument") or r.get("instrument_key") or "")
        )
        if not dt or not inst:
            continue
        raw = r.get("weight", r.get("target_weight"))
        if raw is None:
            continue
        out[(dt, inst)] = float(raw)
    return out


def diff_portfolio(
    qd_rows: Sequence[Mapping[str, Any]],
    qlib_rows: Sequence[Mapping[str, Any]],
    *,
    abs_tol: float = 1e-8,
) -> LayerResult:
    """比较 target weights（NUMERIC）。"""
    a = _index_weights(qd_rows)
    b = _index_weights(qlib_rows)
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

    # 日度权重和（cash = 1 - long）
    by_day_a: dict[str, float] = {}
    for (dt, _i), w in a.items():
        by_day_a[dt] = by_day_a.get(dt, 0.0) + w
    details: dict[str, Any] = {
        "n_qd": len(a),
        "n_qlib": len(b),
        "n_common": len(common),
        "n_only_qd": len(only_a),
        "n_only_qlib": len(only_b),
        "long_weight_by_day_qd": by_day_a,
    }
    if not a and not b:
        return LayerResult(
            layer="portfolio",
            kind="NUMERIC",
            status="PASS",
            message="both empty",
            details=details,
        )
    if only_a or only_b or max_abs > abs_tol:
        return LayerResult(
            layer="portfolio",
            kind="NUMERIC",
            status="FAIL",
            message="portfolio weight mismatch",
            max_abs_diff=max_abs,
            first_divergence=first,
            details=details,
        )
    return LayerResult(
        layer="portfolio",
        kind="NUMERIC",
        status="PASS",
        message="portfolio weights aligned",
        max_abs_diff=max_abs,
        details=details,
    )
