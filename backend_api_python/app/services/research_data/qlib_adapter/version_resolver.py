"""VersionResolver：冻结 Dataset / Processor / Adapter 身份与 bundle_hash。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.services.research_data.contracts import DatasetHandle, PricePolicy, ProcessorDefinition
from app.services.research_data.data_query import DataQuery
from app.services.research_data.qlib_materializer.identity import MATERIALIZER_VERSION
from app.services.research_data.registry import ResearchRegistry

from .errors import VersionResolveError
from .processor_adapter import compute_pipeline_digest
from .version import ADAPTER_VERSION


@dataclass(frozen=True)
class ResearchBundleIdentity:
    """一次研究运行冻结的版本指纹。"""

    dataset_ref: str
    dataset_hash: str
    bundle_hash: str
    adapter_version: str
    materializer_version: str
    processor_version: str
    pipeline_digest: str
    snapshot_id: str
    schema_version: str
    price_policy: dict[str, Any]
    handle: DatasetHandle
    processor: ProcessorDefinition | None


def compute_bundle_hash(
    *,
    dataset_hash: str,
    adapter_version: str,
    processor_version: str,
    pipeline_digest: str = "none",
) -> str:
    """Experiment 复现键；含 pipeline 内容指纹，不改 Domain dataset_hash。"""
    payload = f"{dataset_hash}|{adapter_version}|{processor_version}|{pipeline_digest}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class VersionResolver:
    """从 DataQuery + Registry 解析研究包身份。"""

    def __init__(self, query: DataQuery, registry: ResearchRegistry | None = None) -> None:
        self._query = query
        # registry 可选；缺省时仅用 dataset.processor 字符串，不强制加载 ProcessorDefinition
        self._registry = registry if registry is not None else getattr(query, "_registry", None)

    def resolve(self, dataset_ref: str) -> ResearchBundleIdentity:
        """解析 dataset_ref → ResearchBundleIdentity。"""
        try:
            handle = self._query.dataset(dataset_ref)
        except Exception as exc:
            raise VersionResolveError(f"cannot load dataset {dataset_ref!r}: {exc}") from exc

        definition = handle.definition
        processor_ref = (definition.processor or "").strip() or "none"
        processor_def: ProcessorDefinition | None = None

        if processor_ref != "none":
            if self._registry is None:
                raise VersionResolveError(
                    f"processor {processor_ref!r} set but registry unavailable"
                )
            try:
                processor_def = self._registry.get_processor(processor_ref)
            except Exception as exc:
                raise VersionResolveError(
                    f"processor not found: {processor_ref!r}: {exc}"
                ) from exc
                    # 规范化为 code@version
            processor_ref = f"{processor_def.code}@{processor_def.version}"

        digest = compute_pipeline_digest(
            processor_def.pipeline if processor_def is not None else None
        )

        policy = definition.price_policy
        if isinstance(policy, PricePolicy):
            policy_dict = policy.model_dump(mode="json")
        else:
            policy_dict = dict(policy or {})

        bundle = compute_bundle_hash(
            dataset_hash=handle.dataset_hash,
            adapter_version=ADAPTER_VERSION,
            processor_version=processor_ref,
            pipeline_digest=digest,
        )
        return ResearchBundleIdentity(
            dataset_ref=dataset_ref,
            dataset_hash=handle.dataset_hash,
            bundle_hash=bundle,
            adapter_version=ADAPTER_VERSION,
            materializer_version=MATERIALIZER_VERSION,
            processor_version=processor_ref,
            pipeline_digest=digest,
            snapshot_id=definition.snapshot_id,
            schema_version=definition.schema_version,
            price_policy=policy_dict,
            handle=handle,
            processor=processor_def,
        )
