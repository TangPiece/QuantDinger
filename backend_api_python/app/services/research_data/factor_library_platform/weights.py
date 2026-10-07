"""Portfolio 权重：EQUAL / ICIR / RISK / CORR_ADJUSTED（薄层）。"""

from __future__ import annotations

import math
from typing import Mapping

from .protocol import WeightMethod


def resolve_portfolio_weights(
    member_refs: list[str],
    *,
    method: WeightMethod,
    metrics: Mapping[str, Mapping[str, float]] | None = None,
    corr_matrix: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, float]:
    refs = list(member_refs)
    n = len(refs)
    if n == 0:
        return {}
    metrics = metrics or {}

    if method == "EQUAL":
        w = 1.0 / n
        return {r: w for r in refs}

    if method == "ICIR":
        raw = [max(float(metrics.get(r, {}).get("icir", metrics.get(r, {}).get("icir_score", 0.0))), 0.0) for r in refs]
        s = sum(raw)
        if s <= 0:
            w = 1.0 / n
            return {r: w for r in refs}
        return {r: raw[i] / s for i, r in enumerate(refs)}

    if method == "RISK":
        raw = []
        for r in refs:
            vol = float(metrics.get(r, {}).get("volatility", metrics.get(r, {}).get("risk", 1.0)))
            vol = max(vol, 1e-6)
            raw.append(1.0 / vol)
        s = sum(raw)
        return {r: raw[i] / s for i, r in enumerate(refs)}

    if method == "CORR_ADJUSTED":
        base = resolve_portfolio_weights(refs, method="ICIR", metrics=metrics)
        if not corr_matrix or n < 2:
            return base
        adj = dict(base)
        for i, a in enumerate(refs):
            penalty = 0.0
            for b in refs:
                if a == b:
                    continue
                c = abs(float((corr_matrix.get(a) or {}).get(b, 0.0)))
                penalty += c * adj.get(b, 0.0)
            adj[a] = max(adj[a] * (1.0 - 0.5 * penalty), 0.0)
        s = sum(adj.values())
        if s <= 0 or any(math.isnan(x) for x in adj.values()):
            w = 1.0 / n
            return {r: w for r in refs}
        return {r: adj[r] / s for r in refs}

    raise ValueError(f"unsupported weight_method={method!r}")


__all__ = ["resolve_portfolio_weights"]
