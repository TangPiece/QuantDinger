"""逐日 Gram-Schmidt 正交化后再等权合成。"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .protocol import CombinationSpec, CompositeRow, NormalizedRow


class GramSchmidtOrtho:
    """按 member 顺序对截面列做 Gram-Schmidt，再 EQUAL 合成。"""

    def combine(
        self, rows: list[NormalizedRow], spec: CombinationSpec
    ) -> list[CompositeRow]:
        ids = list(spec.member_factor_dataset_ids)
        by_date: dict = defaultdict(list)
        for r in rows:
            by_date[r.trading_date].append(r)

        out: list[CompositeRow] = []
        n_f = len(ids)
        w = 1.0 / n_f
        for d in sorted(by_date):
            day = by_date[d]
            # X shape (n_stocks, n_factors)
            X = np.column_stack(
                [np.asarray([r.values[mid] for r in day], dtype=float) for mid in ids]
            )
            Q = np.zeros_like(X)
            for j in range(n_f):
                v = X[:, j].copy()
                for k in range(j):
                    qk = Q[:, k]
                    denom = float(np.dot(qk, qk))
                    if denom <= 1e-18:
                        continue
                    v = v - (np.dot(qk, v) / denom) * qk
                # 不强制单位化，保留尺度；全零列保持零
                Q[:, j] = v
            # EQUAL on orthogonal columns
            c = Q @ np.full(n_f, w)
            for i, r in enumerate(day):
                out.append(
                    CompositeRow(
                        trading_date=d,
                        instrument_key=r.instrument_key,
                        composite=float(c[i]),
                        member_values={
                            mid: float(Q[i, j]) for j, mid in enumerate(ids)
                        },
                    )
                )
        return out
