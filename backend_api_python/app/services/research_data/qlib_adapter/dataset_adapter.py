"""DatasetAdapter / QlibAdapter：Domain Dataset → Qlib Handler / DatasetH。

业务唯一构造面；禁止绕过本模块直接 qlib.init。
Phase 2B：ResearchDatasetSpec → QuantDingerQLibHandler → DatasetH(train/valid/test)。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.research_data.data_query import DataQuery
from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.protocol import MaterializationResult
from app.services.research_data.registry import ResearchRegistry

from .dataset_cache import DatasetArtifactCache, compute_dataset_artifact_id
from .errors import QlibAdapterError
from .feature_adapter import FeatureAdapter
from .handler import HandlerBuilder, QuantDingerQLibHandler
from .label_adapter import LabelAdapter
from .processor_adapter import ProcessorAdapter
from .runtime import QlibRuntime, default_runtime
from .specs import ResearchDatasetSpec, SegmentSpec
from .version_resolver import ResearchBundleIdentity, VersionResolver


class QlibAdapter:
    """QuantDinger → Qlib 适配器门面。"""

    def __init__(
        self,
        query: DataQuery,
        *,
        materializer: DefaultQlibMaterializer | None = None,
        runtime: QlibRuntime | None = None,
        registry: ResearchRegistry | None = None,
        cache_root=None,
        dataset_cache_root=None,
        start: date | None = None,
        end: date | None = None,
    ) -> None:
        self._query = query
        self._registry = registry if registry is not None else getattr(query, "_registry", None)
        self._runtime = runtime or default_runtime
        self._materializer = materializer or DefaultQlibMaterializer(
            query, cache_root=cache_root, start=start, end=end
        )
        self._features = FeatureAdapter()
        self._labels = LabelAdapter()
        self._processors = ProcessorAdapter(self._registry)
        self._versions = VersionResolver(query, self._registry)
        self._start = start
        self._end = end
        self._dataset_cache = DatasetArtifactCache(root=dataset_cache_root)
        self._handler_builder = HandlerBuilder(
            query,
            runtime=self._runtime,
            materializer=self._materializer,
            registry=self._registry,
            versions=self._versions,
            features=self._features,
            labels=self._labels,
            processors=self._processors,
        )

    @property
    def dataset_cache(self) -> DatasetArtifactCache:
        return self._dataset_cache

    def resolve(self, dataset_ref: str) -> ResearchBundleIdentity:
        """解析版本身份（含 dataset_hash / bundle_hash）。"""
        return self._versions.resolve(dataset_ref)

    def ensure_cache(
        self,
        dataset_ref: str,
        *,
        force: bool = False,
    ) -> MaterializationResult:
        """经 Materializer 确保 Qlib Cache READY。"""
        return self._materializer.materialize(dataset_ref, force=force)

    def build_qd_handler(
        self,
        spec: ResearchDatasetSpec,
        *,
        force_materialize: bool | None = None,
    ) -> QuantDingerQLibHandler:
        """Phase 2B：按 ResearchDatasetSpec 构建 QuantDingerQLibHandler。"""
        return self._handler_builder.build(spec, force_materialize=force_materialize)

    def build_handler(
        self,
        dataset_ref: str | ResearchDatasetSpec,
        *,
        start: date | str | None = None,
        end: date | str | None = None,
        force_materialize: bool = False,
        instruments: list[str] | None = None,
    ) -> Any:
        """构建 DataHandlerLP。

        - 传入 ResearchDatasetSpec → QuantDingerQLibHandler.inner（含 label）
        - 传入 dataset_ref 字符串 → 2A 兼容最小 Handler（仅 feature）
        """
        if isinstance(dataset_ref, ResearchDatasetSpec):
            qd = self.build_qd_handler(dataset_ref, force_materialize=force_materialize)
            return qd.inner

        try:
            from qlib.data.dataset.handler import DataHandlerLP
        except ImportError as exc:
            raise QlibAdapterError("pyqlib required for build_handler") from exc

        bundle = self.resolve(dataset_ref)
        cache = self.ensure_cache(dataset_ref, force=force_materialize)
        self._runtime.activate(cache.cache_path, kernels=1)

        definition = bundle.handle.definition
        start_d = _as_date(start) or self._start or date(1970, 1, 1)
        end_d = _as_date(end) or self._end or date(2100, 1, 1)

        if instruments is None:
            members = self._query.universe(
                definition.universe_code,
                end_d,
                snapshot_id=definition.snapshot_id,
                universe_version=definition.universe_version,
            )
        else:
            members = list(instruments)
        if not members:
            raise QlibAdapterError("empty universe for handler")

        qlib_insts = [to_qlib_instrument(ik).lower() for ik in members]
        raw_feats = list(definition.features) or [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        ]
        qlib_fields = self._features.to_qlib_fields(raw_feats)
        learn_p, infer_p = self._processors.build_handler_processors(bundle.processor)

        # 需 fit 的 processor 禁止走无 train 段的 2A 字符串路径（避免 silent 全样本 fit）
        if self._processors.definition_needs_fit(bundle.processor):
            raise QlibAdapterError(
                "processor requires train fit window; "
                "use ResearchDatasetSpec (segments.train) instead of build_handler(str)"
            )

        return DataHandlerLP(
            instruments=qlib_insts,
            start_time=start_d.isoformat(),
            end_time=end_d.isoformat(),
            data_loader={
                "class": "QlibDataLoader",
                "kwargs": {
                    "config": {
                        "feature": qlib_fields,
                    },
                },
            },
            learn_processors=learn_p,
            infer_processors=infer_p,
        )

    def build_dataset(
        self,
        dataset_ref: str | ResearchDatasetSpec,
        *,
        start: date | str | None = None,
        end: date | str | None = None,
        force_materialize: bool = False,
        segments: SegmentSpec | None = None,
    ) -> Any:
        """构建 DatasetH。

        Phase 2B：传入 ResearchDatasetSpec → train/valid/test + dataset cache。
        2A 兼容：dataset_ref + 可选单段 start/end。
        """
        try:
            from qlib.data.dataset import DatasetH
        except ImportError as exc:
            raise QlibAdapterError("pyqlib required for build_dataset") from exc

        if isinstance(dataset_ref, ResearchDatasetSpec):
            return self._build_dataset_from_spec(dataset_ref)

        # 若单独传入 SegmentSpec，包装为 ResearchDatasetSpec
        if segments is not None:
            spec = ResearchDatasetSpec(
                dataset_ref=str(dataset_ref),
                segments=segments,
                force_materialize=force_materialize,
            )
            return self._build_dataset_from_spec(spec)

        start_d = _as_date(start) or self._start or date(1970, 1, 1)
        end_d = _as_date(end) or self._end or date(2100, 1, 1)
        handler = self.build_handler(
            str(dataset_ref),
            start=start_d,
            end=end_d,
            force_materialize=force_materialize,
        )
        return DatasetH(
            handler=handler,
            segments={"train": (start_d.isoformat(), end_d.isoformat())},
        )

    def _build_dataset_from_spec(self, spec: ResearchDatasetSpec) -> Any:
        """三段 DatasetH + qlib-dataset-cache 元数据。"""
        from qlib.data.dataset import DatasetH

        bundle = self.resolve(spec.dataset_ref)
        resolved_label, compiled = self._labels.resolve(
            spec.label or bundle.handle.definition.label
        )
        label_json = resolved_label.model_dump(mode="json")

        artifact_id = compute_dataset_artifact_id(
            bundle_hash=bundle.bundle_hash,
            segments=spec.segments.canonical_dict(),
            label=label_json,
        )
        cache_hit = self._dataset_cache.is_ready(artifact_id)

        qd = self.build_qd_handler(spec)
        ds = DatasetH(
            handler=qd.inner,
            segments=spec.segments.to_qlib_segments(),
        )

        self._dataset_cache.write_ready(
            artifact_id,
            dataset_ref=spec.dataset_ref,
            dataset_hash=bundle.dataset_hash,
            bundle_hash=bundle.bundle_hash,
            segments=spec.segments.canonical_dict(),
            label=label_json,
            materialization_id=qd.materialization.materialization_id,
            qlib_cache_path=qd.materialization.cache_path,
            extra={
                "cache_hit": bool(cache_hit and not spec.force_materialize),
                "label_expression": compiled.qlib_expression,
                "instrument_count": len(qd.instruments),
            },
        )

        # 挂载元数据供测试读取
        ds.qd_artifact_id = artifact_id  # type: ignore[attr-defined]
        ds.qd_dataset_hash = bundle.dataset_hash  # type: ignore[attr-defined]
        ds.qd_bundle_hash = bundle.bundle_hash  # type: ignore[attr-defined]
        ds.qd_handler = qd  # type: ignore[attr-defined]
        ds.qd_cache_hit = bool(cache_hit and not spec.force_materialize)  # type: ignore[attr-defined]
        return ds

    def fetch_features(
        self,
        dataset_ref: str,
        *,
        start: date | str | None = None,
        end: date | str | None = None,
        force_materialize: bool = False,
    ):
        """便捷：build_handler + fetch(feature)。"""
        handler = self.build_handler(
            dataset_ref,
            start=start,
            end=end,
            force_materialize=force_materialize,
        )
        try:
            df = handler.fetch(col_set="feature")
        except Exception:
            df = handler.fetch()
        if df is None or len(df) == 0:
            raise QlibAdapterError("handler.fetch returned empty")
        return df


def _as_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# 别名：计划中的 DatasetAdapter 即门面
DatasetAdapter = QlibAdapter
