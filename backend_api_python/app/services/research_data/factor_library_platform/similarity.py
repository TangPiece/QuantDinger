"""Similarity：注入矩阵或 catalog 内 pairwise corr。"""

from __future__ import annotations

from typing import Mapping

from .protocol import FactorLibraryInject, SimilarFactorHit


def similar_factors(
    factor_ref: str,
    *,
    catalog_refs: list[str],
    inject: FactorLibraryInject | None = None,
    top_k: int = 10,
    corr_matrix: Mapping[str, Mapping[str, float]] | None = None,
) -> list[SimilarFactorHit]:
    if inject and factor_ref in inject.similarity_overrides:
        hits = list(inject.similarity_overrides[factor_ref])
        return hits[:top_k]

    matrix = corr_matrix
    if matrix is None and inject and inject.cluster_corr_matrix:
        matrix = inject.cluster_corr_matrix

    hits: list[SimilarFactorHit] = []
    if matrix:
        row = matrix.get(factor_ref) or {}
        for ref, c in row.items():
            if ref == factor_ref:
                continue
            hits.append(SimilarFactorHit(factor_ref=ref, corr=float(c), source="corr_matrix"))
        hits.sort(key=lambda h: abs(h.corr), reverse=True)
        return hits[:top_k]

    for ref in catalog_refs:
        if ref == factor_ref:
            continue
        hits.append(SimilarFactorHit(factor_ref=ref, corr=0.0, source="catalog_stub"))
    return hits[:top_k]


__all__ = ["similar_factors"]
