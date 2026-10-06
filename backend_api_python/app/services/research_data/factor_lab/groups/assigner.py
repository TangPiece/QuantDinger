"""Cross-sectional average-rank → quantile groups（等权）。"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime
from typing import Any, Sequence

import pandas as pd

from .protocol import GroupSpec, MembershipRow

_FORWARD_RE = re.compile(r"^forward_return_(\d+)d$")


def infer_horizons(records: Sequence[dict[str, Any]]) -> list[int]:
    found: set[int] = set()
    for r in records:
        for k in r:
            m = _FORWARD_RE.match(str(k))
            if m:
                found.add(int(m.group(1)))
    return sorted(found)


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _is_nan(v: Any) -> bool:
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True


def _average_ranks(values: list[float]) -> list[float]:
    """平均秩；禁止 method=first 人为破 tie。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _group_from_rank(rank: float, n: int, n_g: int) -> int:
    """因子越高 rank 越大 → G1；ties 允许组规模不平衡。"""
    pct = rank / n
    bucket_low_first = min(n_g, max(1, math.ceil(pct * n_g)))
    return int(n_g + 1 - bucket_low_first)


class GroupAssigner:
    """每日 × horizon 分位；G1=最高因子，GN=最低。"""

    def assign(
        self,
        records: Sequence[dict[str, Any]],
        spec: GroupSpec,
    ) -> list[MembershipRow]:
        allowed = set(spec.allowed_sample_status)
        horizons = list(spec.horizons) if spec.horizons else infer_horizons(records)
        if not horizons:
            return []

        rows: list[dict[str, Any]] = []
        for r in records:
            if str(r.get("sample_status") or "") not in allowed:
                continue
            fv = r.get("factor_value", r.get("value"))
            if _is_nan(fv):
                continue
            item = {
                "instrument_key": str(r["instrument_key"]),
                "factor_date": _as_date(r.get("factor_date") or r.get("evaluation_date")),
                "factor_value": float(fv),
            }
            for h in horizons:
                col = f"forward_return_{h}d"
                rv = r.get(col)
                item[col] = None if _is_nan(rv) else float(rv)
            rows.append(item)
        if not rows:
            return []

        df = pd.DataFrame(rows)
        n_g = int(spec.group_count)
        min_cs = int(spec.min_cross_section_size)
        out: list[MembershipRow] = []

        for day, gday in df.groupby("factor_date", sort=True):
            d = _as_date(day)
            # 分组基于当日全部有 factor 的股票
            if len(gday) < min_cs:
                continue
            vals = gday["factor_value"].astype(float).tolist()
            ranks = _average_ranks(vals)
            n = len(vals)
            iks = gday["instrument_key"].astype(str).tolist()
            fvals = vals
            group_map: dict[str, tuple[int, float, float]] = {}
            for i, ik in enumerate(iks):
                grp = _group_from_rank(ranks[i], n, n_g)
                group_map[ik] = (grp, ranks[i], fvals[i])

            for h in horizons:
                col = f"forward_return_{h}d"
                members: list[tuple[str, int, float, float]] = []
                for _, row in gday.iterrows():
                    ik = str(row["instrument_key"])
                    if ik not in group_map:
                        continue
                    if _is_nan(row.get(col)):
                        continue
                    grp, frank, fval = group_map[ik]
                    members.append((ik, grp, frank, fval))
                if not members:
                    continue
                sizes = Counter(m[1] for m in members)
                for ik, grp, frank, fval in members:
                    out.append(
                        MembershipRow(
                            evaluation_date=d,
                            horizon=int(h),
                            instrument_key=ik,
                            factor_value=fval,
                            factor_rank=frank,
                            group=int(grp),
                            weight=1.0 / sizes[grp],
                        )
                    )
        return out
