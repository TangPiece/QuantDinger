"""阈值连通分量聚类（基于 corr 矩阵）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from .hashing import compute_cluster_hash
from .identity import new_cluster_id
from .protocol import ENGINE_VERSION, FactorCluster, FactorClusterPolicy


def _build_adjacency(
    refs: list[str],
    matrix: Mapping[str, Mapping[str, float]],
    threshold: float,
) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {r: set() for r in refs}
    for i, a in enumerate(refs):
        for b in refs[i + 1 :]:
            c = abs(float((matrix.get(a) or {}).get(b, 0.0)))
            if c >= threshold:
                adj[a].add(b)
                adj[b].add(a)
    return adj


def _connected_components(refs: list[str], adj: dict[str, set[str]]) -> list[list[str]]:
    seen: set[str] = set()
    out: list[list[str]] = []
    for start in refs:
        if start in seen:
            continue
        stack = [start]
        comp: list[str] = []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            comp.append(node)
            for nb in sorted(adj.get(node, ())):
                if nb not in seen:
                    stack.append(nb)
        out.append(sorted(comp))
    return sorted(out, key=lambda c: c[0] if c else "")


def build_factor_cluster(
    factor_refs: list[str],
    *,
    policy: FactorClusterPolicy,
    corr_matrix: Mapping[str, Mapping[str, float]],
    published_at: datetime | None = None,
) -> FactorCluster:
    refs = sorted(set(factor_refs))
    ts = published_at or datetime.now(timezone.utc)
    thr = float(policy.corr_threshold)
    adj = _build_adjacency(refs, corr_matrix, thr)
    clusters = _connected_components(refs, adj)
    ch = compute_cluster_hash(
        member_refs=refs,
        method=policy.method,
        threshold=thr,
        dataset_hash=policy.dataset_hash,
        policy_version=policy.policy_version,
    )
    return FactorCluster(
        engine_version=ENGINE_VERSION,
        cluster_id=new_cluster_id(),
        cluster_hash=ch,
        method=policy.method,
        corr_threshold=thr,
        dataset_hash=policy.dataset_hash,
        member_refs=refs,
        clusters=clusters,
        published_at=ts,
        metadata={"dataset_ref": policy.dataset_ref},
    )


__all__ = ["build_factor_cluster"]
