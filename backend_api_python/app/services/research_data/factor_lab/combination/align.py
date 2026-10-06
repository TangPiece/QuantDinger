"""多因子日×票 inner join（DROP_ROW）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from .protocol import AlignedRow, CombinationSpec


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    return date.fromisoformat(str(v)[:10])


class CrossSectionAligner:
    """将多个成员面板对齐为 AlignedRow 列表。"""

    def align(
        self,
        member_panels: dict[str, list[dict[str, Any]]],
        spec: CombinationSpec,
    ) -> list[AlignedRow]:
        """inner join：任一成员缺失则丢弃该 (date, instrument)。"""
        ids = list(spec.member_factor_dataset_ids)
        # date -> instrument -> {mid: value}
        grid: dict[date, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for mid in ids:
            for r in member_panels.get(mid, []):
                d = _as_date(r.get("trading_date") or r.get("factor_date"))
                ik = str(r["instrument_key"])
                fv = r.get("value", r.get("factor_value"))
                if fv is None:
                    continue
                try:
                    grid[d][ik][mid] = float(fv)
                except (TypeError, ValueError):
                    continue

        out: list[AlignedRow] = []
        min_n = int(spec.min_cross_section_size)
        for d in sorted(grid):
            day_rows: list[AlignedRow] = []
            for ik, vals in grid[d].items():
                if any(mid not in vals for mid in ids):
                    continue  # DROP_ROW
                day_rows.append(
                    AlignedRow(
                        trading_date=d,
                        instrument_key=ik,
                        values={mid: vals[mid] for mid in ids},
                    )
                )
            if len(day_rows) < min_n:
                continue
            out.extend(day_rows)
        return out
