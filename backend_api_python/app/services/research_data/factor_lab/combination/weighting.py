"""EQUAL / IC_WEIGHT / CORR_ADJUSTED 权重求解。"""

from __future__ import annotations

from .protocol import CombinationSpec, WeightEntry


class WeightSolverError(ValueError):
    pass


class WeightSolver:
    """根据方法与相关矩阵求归一化权重。"""

    def solve(
        self,
        spec: CombinationSpec,
        *,
        corr_matrix: dict[str, dict[str, float]] | None = None,
        member_ic: dict[str, float] | None = None,
    ) -> list[WeightEntry]:
        ids = list(spec.member_factor_dataset_ids)
        n = len(ids)
        ic = dict(member_ic or spec.member_ic or {})

        if spec.weight_method == "EQUAL":
            w = 1.0 / n
            return [WeightEntry(factor_dataset_id=mid, weight=w) for mid in ids]

        if spec.weight_method in ("IC_WEIGHT", "CORR_ADJUSTED"):
            missing = [mid for mid in ids if mid not in ic]
            if missing:
                raise WeightSolverError(
                    f"member_ic missing for {missing}; required by {spec.weight_method}"
                )
            raw: list[float] = []
            for mid in ids:
                base = max(float(ic[mid]), 0.0)
                if spec.weight_method == "CORR_ADJUSTED":
                    mat = corr_matrix or {}
                    others = [abs(mat.get(mid, {}).get(j, 0.0)) for j in ids if j != mid]
                    denom = 1.0 + (sum(others) / len(others) if others else 0.0)
                    raw.append(base / denom)
                else:
                    raw.append(base)
            s = sum(raw)
            if s <= 0.0:
                raise WeightSolverError(
                    "all member_ic <= 0; cannot form IC_WEIGHT / CORR_ADJUSTED"
                )
            return [
                WeightEntry(factor_dataset_id=mid, weight=raw[i] / s)
                for i, mid in enumerate(ids)
            ]

        if spec.weight_method == "ORTHOGONALIZE":
            # 等权占位；实际合成在 orthogonalize 路径
            w = 1.0 / n
            return [WeightEntry(factor_dataset_id=mid, weight=w) for mid in ids]

        raise WeightSolverError(f"unknown weight_method={spec.weight_method!r}")
