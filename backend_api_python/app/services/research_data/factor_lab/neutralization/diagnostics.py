"""Exposure Diagnostics 汇总（跨日均值等）。"""

from __future__ import annotations

import math
from statistics import mean
from typing import Any, Optional

from .protocol import ExposureDiagnostic


def _finite(vals: list[Optional[float]]) -> list[float]:
    out: list[float] = []
    for v in vals:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            continue
        out.append(f)
    return out


class ExposureDiagnosticCalculator:
    """从日度 diagnostic 行聚合 summary JSON。"""

    def summarize(self, rows: list[ExposureDiagnostic]) -> dict[str, Any]:
        """按 exposure_code 聚合 before/after corr 与 R²。"""
        by_code: dict[str, list[ExposureDiagnostic]] = {}
        for r in rows:
            by_code.setdefault(r.exposure_code, []).append(r)
        out: dict[str, Any] = {"by_exposure": {}, "model": {}}
        for code, items in sorted(by_code.items()):
            ok = [x for x in items if x.status == "OK"]
            cb = _finite([x.correlation_before for x in ok])
            ca = _finite([x.correlation_after for x in ok])
            r2s = _finite([x.r_squared for x in ok])
            payload = {
                "mean_correlation_before": mean(cb) if cb else None,
                "mean_correlation_after": mean(ca) if ca else None,
                "mean_r_squared": mean(r2s) if r2s else None,
                "ok_day_count": len(ok),
                "total_day_count": len(items),
            }
            if code == "MODEL":
                out["model"] = payload
            else:
                out["by_exposure"][code] = payload
        # 顶层便利字段
        model_r2 = out.get("model", {}).get("mean_r_squared")
        out["r_squared_mean"] = model_r2
        return out
