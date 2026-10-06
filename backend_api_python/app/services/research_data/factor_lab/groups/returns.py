"""等权 Group Return + Long/Short。"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Literal, Sequence

from .protocol import GroupReturnRow, GroupSpec, MembershipRow


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


class GroupReturnCalculator:
    """G1=high；direction 决定 Long/Short。"""

    def calculate(
        self,
        membership: Sequence[MembershipRow],
        records: Sequence[dict[str, Any]],
        spec: GroupSpec,
        *,
        direction: Literal["POSITIVE", "NEGATIVE"],
    ) -> list[GroupReturnRow]:
        n_g = int(spec.group_count)
        long_g = 1 if direction == "POSITIVE" else n_g
        short_g = n_g if direction == "POSITIVE" else 1

        # (date, ik) → returns by horizon
        ret_map: dict[tuple[date, str], dict[int, float]] = defaultdict(dict)
        for r in records:
            ik = str(r["instrument_key"])
            d = _as_date(r.get("factor_date") or r.get("evaluation_date"))
            for h in {m.horizon for m in membership}:
                col = f"forward_return_{h}d"
                v = r.get(col)
                if not _is_nan(v):
                    ret_map[(d, ik)][int(h)] = float(v)

        # group members: (date, horizon, group) → list returns
        buckets: dict[tuple[date, int, int], list[float]] = defaultdict(list)
        for m in membership:
            rv = ret_map.get((m.evaluation_date, m.instrument_key), {}).get(m.horizon)
            if rv is None:
                continue
            buckets[(m.evaluation_date, m.horizon, m.group)].append(rv)

        keys = sorted({(d, h) for (d, h, _) in buckets})
        out: list[GroupReturnRow] = []
        for d, h in keys:
            g_rets: dict[int, tuple[float, int]] = {}
            for g in range(1, n_g + 1):
                vals = buckets.get((d, h, g), [])
                if vals:
                    g_rets[g] = (sum(vals) / len(vals), len(vals))
            long_r = g_rets.get(long_g, (None, 0))[0]
            short_r = g_rets.get(short_g, (None, 0))[0]
            ls = None
            if long_r is not None and short_r is not None:
                ls = float(long_r) - float(short_r)
            # 每个 group 一行；同时附带 LS 字段便于宽表
            for g in range(1, n_g + 1):
                gr, n = g_rets.get(g, (None, 0))
                out.append(
                    GroupReturnRow(
                        evaluation_date=d,
                        horizon=h,
                        group=g,
                        group_return=gr,
                        sample_count=n,
                        long_return=long_r,
                        short_return=short_r,
                        long_short_return=ls,
                    )
                )
        return out
