"""DatasetAdapter / QlibAdapter：Domain Dataset → Qlib Handler / DatasetH。

业务唯一构造面；禁止绕过本模块直接 qlib.init。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.research_data.data_query import DataQuery
from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.protocol import MaterializationResult
from app.services.research_data.registry import ResearchRegistry

from .errors import QlibAdapterError
from .feature_adapter import FeatureAdapter
from .processor_adapter import ProcessorAdapter
from .runtime import QlibRuntime, default_runtime
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
        self._processors = ProcessorAdapter(self._registry)
        self._versions = VersionResolver(query, self._registry)
        self._start = start
        self._end = end

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

    def build_handler(
        self,
        dataset_ref: str,
        *,
        start: date | str | None = None,
        end: date | str | None = None,
        force_materialize: bool = False,
        instruments: list[str] | None = None,
    ) -> Any:
        """构建最小 DataHandlerLP（无 Alpha158）。

        Returns:
            qlib DataHandlerLP 实例（需已 activate runtime）
        """
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

        # Universe：与 Materializer 一致，用窗口终点 as_of
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

        # Feature 编译：Dataset.features 默认 OHLCV
        raw_feats = list(definition.features) or [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        ]
        # Materializer 只物化原子列；Handler 表达式可含 Ref/Mean 等（基于已物化字段）
        qlib_fields = self._features.to_qlib_fields(raw_feats)

        learn_p, infer_p = self._processors.build_handler_processors(bundle.processor)

        handler = DataHandlerLP(
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
        return handler

    def build_dataset(
        self,
        dataset_ref: str,
        *,
        start: date | str | None = None,
        end: date | str | None = None,
        force_materialize: bool = False,
    ) -> Any:
        """薄封装 DatasetH；单段 train 占位（完整 segments → Phase 2B）。"""
        try:
            from qlib.data.dataset import DatasetH
        except ImportError as exc:
            raise QlibAdapterError("pyqlib required for build_dataset") from exc

        start_d = _as_date(start) or self._start or date(1970, 1, 1)
        end_d = _as_date(end) or self._end or date(2100, 1, 1)
        handler = self.build_handler(
            dataset_ref,
            start=start_d,
            end=end_d,
            force_materialize=force_materialize,
        )
        return DatasetH(
            handler=handler,
            segments={
                "train": (start_d.isoformat(), end_d.isoformat()),
            },
        )

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
