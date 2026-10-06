"""加权合成 Composite。"""

from __future__ import annotations

from .protocol import CombinationSpec, CompositeRow, NormalizedRow, WeightEntry


class WeightedCombiner:
    """c = Σ w_i * x_i_norm。"""

    def combine(
        self,
        rows: list[NormalizedRow],
        weights: list[WeightEntry],
        spec: CombinationSpec,
    ) -> list[CompositeRow]:
        wmap = {w.factor_dataset_id: float(w.weight) for w in weights}
        ids = list(spec.member_factor_dataset_ids)
        out: list[CompositeRow] = []
        for r in rows:
            c = 0.0
            for mid in ids:
                c += wmap.get(mid, 0.0) * float(r.values[mid])
            out.append(
                CompositeRow(
                    trading_date=r.trading_date,
                    instrument_key=r.instrument_key,
                    composite=c,
                    member_values=dict(r.values),
                )
            )
        return out
