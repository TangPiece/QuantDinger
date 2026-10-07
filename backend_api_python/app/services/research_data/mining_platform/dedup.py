"""表达式 hash 去重 + 可选相关冗余。"""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import FactorCandidate, MiningPlatformInject


@dataclass
class DedupResult:
    survivors: list[FactorCandidate]
    removed_expression_dup: int
    marked_redundant: int


def dedup_by_expression_hash(candidates: list[FactorCandidate]) -> tuple[list[FactorCandidate], int]:
    seen: set[str] = set()
    out: list[FactorCandidate] = []
    removed = 0
    for c in candidates:
        if c.expression_hash in seen:
            c = c.model_copy(update={"status": "DEDUP_REMOVED"})
            removed += 1
            continue
        seen.add(c.expression_hash)
        out.append(c)
    return out, removed


def apply_corr_redundancy(
    ranked: list[FactorCandidate],
    *,
    threshold: float,
    top_n: int,
    inject: MiningPlatformInject | None = None,
) -> tuple[list[FactorCandidate], int]:
    """对 top-N 按 expression_hash 伪相关标记 REDUNDANT（inject 可覆盖）。"""
    marked = 0
    if inject and inject.corr_pairs_redundant:
        redundant_hashes: set[str] = set()
        by_id = {c.candidate_id: c for c in ranked}
        for a, b in inject.corr_pairs_redundant:
            ca = by_id.get(a)
            cb = by_id.get(b)
            if ca and cb:
                redundant_hashes.add(cb.expression_hash)
        out: list[FactorCandidate] = []
        for c in ranked:
            if c.expression_hash in redundant_hashes:
                c = c.model_copy(
                    update={"status": "REDUNDANT", "redundant_with": c.redundant_with or "inject"}
                )
                marked += 1
            out.append(c)
        return out, marked

    # 无真实 factor 矩阵时用 hash 相邻对模拟高相关
    slice_ = ranked[:top_n]
    out_map = {c.candidate_id: c for c in ranked}
    for i in range(1, len(slice_)):
        prev = slice_[i - 1]
        cur = slice_[i]
        h1 = int(prev.expression_hash[:8], 16)
        h2 = int(cur.expression_hash[:8], 16)
        pseudo_corr = 1.0 - abs(h1 - h2) / float(2**32)
        if pseudo_corr >= threshold:
            out_map[cur.candidate_id] = cur.model_copy(
                update={
                    "status": "REDUNDANT",
                    "redundant_with": prev.candidate_id,
                    "metadata": {**cur.metadata, "pseudo_corr": pseudo_corr},
                }
            )
            marked += 1
    return [out_map[c.candidate_id] for c in ranked], marked


def run_dedup(
    candidates: list[FactorCandidate],
    *,
    dedup_expression: bool,
    corr_enabled: bool,
    corr_threshold: float,
    corr_top_n: int,
    inject: MiningPlatformInject | None = None,
) -> DedupResult:
    working = list(candidates)
    removed = 0
    if dedup_expression:
        working, removed = dedup_by_expression_hash(working)
        working = [c for c in working if c.status != "DEDUP_REMOVED"]
    marked = 0
    if corr_enabled and working:
        working, marked = apply_corr_redundancy(
            working,
            threshold=corr_threshold,
            top_n=corr_top_n,
            inject=inject,
        )
    return DedupResult(
        survivors=working,
        removed_expression_dup=removed,
        marked_redundant=marked,
    )


__all__ = ["DedupResult", "run_dedup"]
