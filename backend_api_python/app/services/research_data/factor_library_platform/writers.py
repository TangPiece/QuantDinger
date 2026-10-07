"""写入 LibraryEntry / Collection / Portfolio / Cluster。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .artifact_store import LibraryArtifactStore
from .protocol import FactorCluster, FactorCollection, FactorLibraryEntry, FactorPortfolioSpec


@dataclass
class WriteResult:
    path: str
    checksum: str


def _write_json(path, model) -> WriteResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def write_entry(store: LibraryArtifactStore, entry: FactorLibraryEntry) -> WriteResult:
    return _write_json(store.entry_path(entry_id=entry.entry_id), entry)


def write_collection(store: LibraryArtifactStore, coll: FactorCollection) -> WriteResult:
    return _write_json(store.collection_path(collection_id=coll.collection_id), coll)


def write_portfolio(store: LibraryArtifactStore, spec: FactorPortfolioSpec) -> WriteResult:
    return _write_json(store.portfolio_path(portfolio_id=spec.portfolio_id), spec)


def write_cluster(store: LibraryArtifactStore, cluster: FactorCluster) -> WriteResult:
    return _write_json(store.cluster_path(cluster_id=cluster.cluster_id), cluster)


__all__ = [
    "WriteResult",
    "write_cluster",
    "write_collection",
    "write_entry",
    "write_portfolio",
]
