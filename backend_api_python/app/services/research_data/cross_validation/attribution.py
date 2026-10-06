"""差异归因：把收益差映射到已知层。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .protocol import AttributionBreakdown, LayerResult


def attribute_differences(
    layers: Sequence[LayerResult],
    *,
    qd_total_return: float | None,
    qlib_total_return: float | None,
    compatibility: Mapping[str, Any] | None = None,
    realism: str = "GROSS",
    other_tol: float = 1e-3,
) -> AttributionBreakdown:
    """GROSS：L1–L5 PASS → data/signal/portfolio=0；残余 → execution/other。

    NET：compatibility PARTIAL/UNSUPPORTED → cost 记 EXPECTED。
    """
    by = {L.layer: L for L in layers}
    total = 0.0
    if qd_total_return is not None and qlib_total_return is not None:
        total = float(qd_total_return) - float(qlib_total_return)

    notes: list[str] = []
    data = signal = portfolio = execution = cost = 0.0

    def _failed(name: str) -> bool:
        L = by.get(name)
        return bool(L and L.status == "FAIL")

    if _failed("dataset"):
        data = total
        notes.append("dataset FAIL absorbs delta")
    elif _failed("signal"):
        signal = total
        notes.append("signal FAIL absorbs delta")
    elif _failed("portfolio"):
        portfolio = total
        notes.append("portfolio FAIL absorbs delta")
    else:
        # 上游对齐：差来自执行路径 / 成本模型
        if realism == "NET" and compatibility:
            items = compatibility.get("items") or []
            has_cost = any(
                str(it.get("capability") or "").startswith("commission")
                or str(it.get("level")) in ("PARTIAL", "UNSUPPORTED")
                for it in items
            )
            if has_cost:
                cost = total * 0.7
                execution = total * 0.2
                notes.append("NET: majority attributed to cost model EXPECTED_DIFFERENCE")
            else:
                execution = total
        else:
            # GROSS：合成 close-to-close vs NEXT_OPEN mark 的已知语义差
            nav_L = by.get("nav")
            if nav_L and nav_L.status == "PASS":
                execution = total
                notes.append("GROSS: residual assigned to execution fill semantics")
            elif nav_L and nav_L.status == "FAIL":
                execution = total * 0.8
                notes.append("NAV FAIL: primary execution path")
            else:
                execution = total

    other = total - (data + signal + portfolio + execution + cost)
    # 浮点收口
    if abs(other) < 1e-12:
        other = 0.0

    if abs(other) > other_tol and not notes:
        notes.append("unexplained residual exceeds other_tol")

    return AttributionBreakdown(
        data=float(data),
        signal=float(signal),
        portfolio=float(portfolio),
        execution=float(execution),
        cost=float(cost),
        other=float(other),
        total=float(total),
        notes=notes,
    )
