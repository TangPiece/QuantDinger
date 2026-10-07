"""Factor / FeatureSet 血缘：正向与反向索引。"""

from __future__ import annotations

from typing import Any, Protocol

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.factor_lab.dependencies import parse_dependency

from .protocol import LineageNode
from .taxonomy import AssetKind, read_asset_kind


class _RegistryLike(Protocol):
    def get_feature(self, feature_ref: str) -> FeatureDefinition: ...

    def get_dataset(self, dataset_ref: str) -> Any: ...

    def get_factor_dataset(self, factor_dataset_id: str) -> Any: ...


def build_lineage(
    registry: _RegistryLike,
    ref: str,
    *,
    dataset_ref: str | None = None,
) -> LineageNode:
    """Factor → deps → Feature → dataset_hash / snapshot_id。"""
    feat = registry.get_feature(ref)
    kind = read_asset_kind(feat)
    root = LineageNode(
        ref=ref,
        kind=kind.value,
        hash_value=str(feat.factor_hash or ""),
    )
    for raw in feat.dependencies or []:
        dep = parse_dependency(raw)
        if dep.dependency_type == "factor":
            child = build_lineage(registry, dep.dependency_code)
            root.children.append(child)
        else:
            root.children.append(
                LineageNode(
                    ref=f"{dep.dependency_type}:{dep.dependency_code}",
                    kind="DATA",
                )
            )
    if dataset_ref:
        try:
            handle = registry.get_dataset(dataset_ref)
            root.children.append(
                LineageNode(
                    ref=dataset_ref,
                    kind="DATASET",
                    hash_value=str(handle.dataset_hash or ""),
                    children=[
                        LineageNode(
                            ref=handle.definition.snapshot_id,
                            kind="SNAPSHOT",
                        )
                    ],
                )
            )
        except Exception:
            pass
    return root


def list_by_dataset(registry: Any, dataset_hash: str) -> list[str]:
    """反向：dataset_hash → factor_ref 列表（FactorDataset + build 扫描）。"""
    target = str(dataset_hash or "").strip()
    if not target:
        return []
    out: set[str] = set()
    if hasattr(registry, "_read"):
        data = registry._read()  # type: ignore[attr-defined]
        for _fid, raw in (data.get("factor_datasets") or {}).items():
            if str(raw.get("dataset_hash") or "") == target:
                ref = str(raw.get("factor_ref") or "")
                if ref:
                    out.add(ref)
        for _ref, raw in (data.get("features") or {}).items():
            sidecar = raw.get("definition") or {}
            builds = sidecar.get("_platform_builds") or []
            for b in builds:
                if str(b.get("dataset_hash") or "") == target:
                    out.add(str(b.get("factor_ref") or _ref))
    return sorted(out)


__all__ = ["build_lineage", "list_by_dataset"]
