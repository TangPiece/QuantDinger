"""Performance metrics Diff。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import LayerResult

_KEYS = (
    "total_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe",
    "max_drawdown",
)


def diff_performance(
    qd_metrics: Mapping[str, Any] | None,
    qlib_metrics: Mapping[str, Any] | None,
    *,
    abs_tol: float = 0.05,
) -> LayerResult:
    """比较摘要绩效指标（有则比）。"""
    qd = dict(qd_metrics or {})
    ql = dict(qlib_metrics or {})
    side: dict[str, Any] = {}
    max_abs = 0.0
    first = ""
    fail = False
    for k in _KEYS:
        va = qd.get(k)
        vb = ql.get(k)
        side[k] = {"qd": va, "qlib": vb}
        if va is None or vb is None:
            continue
        try:
            fa, fb = float(va), float(vb)
        except (TypeError, ValueError):
            continue
        d = abs(fa - fb)
        if d > max_abs:
            max_abs = d
        if d > abs_tol and not first:
            first = k
            fail = True
    # 至少 total_return 两侧都有才严格；否则仅 PASS with note
    if qd.get("total_return") is None or ql.get("total_return") is None:
        return LayerResult(
            layer="performance",
            kind="NUMERIC",
            status="PASS" if not fail else "FAIL",
            message="partial metrics",
            max_abs_diff=max_abs,
            first_divergence=first,
            details={"side_by_side": side},
        )
    if fail:
        return LayerResult(
            layer="performance",
            kind="NUMERIC",
            status="FAIL",
            message="performance mismatch",
            max_abs_diff=max_abs,
            first_divergence=first,
            details={"side_by_side": side},
        )
    return LayerResult(
        layer="performance",
        kind="NUMERIC",
        status="PASS",
        message="performance within tolerance",
        max_abs_diff=max_abs,
        details={"side_by_side": side},
    )


def build_side_by_side(
    qd_metrics: Mapping[str, Any] | None,
    qlib_metrics: Mapping[str, Any] | None,
    *,
    universe_n: int | None = None,
    turnover_qd: float | None = None,
    turnover_ql: float | None = None,
) -> dict[str, Any]:
    """报告用对照表。"""
    qd = dict(qd_metrics or {})
    ql = dict(qlib_metrics or {})
    return {
        "universe": {"qd": universe_n, "qlib": universe_n},
        "turnover": {"qd": turnover_qd, "qlib": turnover_ql},
        "total_return": {"qd": qd.get("total_return"), "qlib": ql.get("total_return")},
        "annualized_volatility": {
            "qd": qd.get("annualized_volatility"),
            "qlib": ql.get("annualized_volatility"),
        },
        "sharpe": {"qd": qd.get("sharpe"), "qlib": ql.get("sharpe")},
        "max_drawdown": {"qd": qd.get("max_drawdown"), "qlib": ql.get("max_drawdown")},
    }
