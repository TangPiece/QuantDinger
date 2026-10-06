"""L7 NAV 逐日 Diff。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .protocol import LayerResult


def _index_nav(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        dt = str(r.get("trading_date") or "")[:10]
        if not dt:
            continue
        try:
            out[dt] = float(r["nav"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def diff_nav(
    qd_curve: Sequence[Mapping[str, Any]],
    qlib_curve: Sequence[Mapping[str, Any]],
    *,
    abs_tol: float = 0.05,
    rel_tol: float = 0.05,
) -> LayerResult:
    """逐日比较 NAV；记录 first divergence。"""
    a = _index_nav(qd_curve)
    b = _index_nav(qlib_curve)
    common = sorted(set(a) & set(b))
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    max_abs = 0.0
    max_rel = 0.0
    first = ""
    day_rows: list[dict[str, Any]] = []
    for dt in common:
        qa, qb = a[dt], b[dt]
        ad = abs(qa - qb)
        rd = ad / max(abs(qa), 1e-12)
        if ad > max_abs:
            max_abs = ad
        if rd > max_rel:
            max_rel = rd
        if (ad > abs_tol and rd > rel_tol) and not first:
            first = dt
        day_rows.append(
            {
                "date": dt,
                "qd_nav": qa,
                "qlib_nav": qb,
                "absolute_diff": ad,
                "relative_diff": rd,
            }
        )

    details: dict[str, Any] = {
        "n_qd": len(a),
        "n_qlib": len(b),
        "n_common": len(common),
        "n_only_qd": len(only_a),
        "n_only_qlib": len(only_b),
        "days": day_rows[:32],
    }

    if not a or not b:
        return LayerResult(
            layer="nav",
            kind="NUMERIC",
            status="FAIL",
            message="missing nav curve on one side",
            details=details,
        )

    # 日期集合可略差（执行映射）；要求公共日在 tol 内
    fail = False
    if common:
        for row in day_rows:
            if row["absolute_diff"] > abs_tol and row["relative_diff"] > rel_tol:
                fail = True
                break
    else:
        fail = True

    # 最终 NAV 同向辅助
    if a and b:
        qa = a[max(a)]
        qb = b[max(b)]
        details["final_qd_nav"] = qa
        details["final_qlib_nav"] = qb
        # 相对初始 1.0 的收益同向（若都偏离）
        if (qa - 1.0) * (qb - 1.0) < 0 and abs(qa - qb) > abs_tol:
            fail = True
            details["direction_mismatch"] = True

    if fail:
        return LayerResult(
            layer="nav",
            kind="NUMERIC",
            status="FAIL",
            message="nav divergence",
            max_abs_diff=max_abs,
            max_rel_diff=max_rel,
            first_divergence=first,
            details=details,
        )
    return LayerResult(
        layer="nav",
        kind="NUMERIC",
        status="PASS",
        message="nav within tolerance",
        max_abs_diff=max_abs,
        max_rel_diff=max_rel,
        first_divergence=first,
        details=details,
    )
