"""QuantDingerQLibHandler：feature + label + processor + universe snapshot。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from unittest.mock import MagicMock

from app.services.research_data.contracts import LabelDefinition
from app.services.research_data.data_query import DataQuery
from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.protocol import MaterializationResult
from app.services.research_data.registry import ResearchRegistry

from .errors import QlibAdapterError
from .feature_adapter import FeatureAdapter
from .label_adapter import CompiledLabel, LabelAdapter
from .processor_adapter import ProcessorAdapter
from .runtime import QlibRuntime
from .specs import ResearchDatasetSpec
from .version_resolver import ResearchBundleIdentity, VersionResolver


@dataclass
class QuantDingerQLibHandler:
    """QuantDinger 研究 DataHandler 包装（内部为 Qlib DataHandlerLP）。

    不暴露裸 qlib.init；由 QlibAdapter / Runtime 激活 provider。
    """

    inner: Any
    bundle: ResearchBundleIdentity
    materialization: MaterializationResult
    label: LabelDefinition
    compiled_label: CompiledLabel
    instruments: list[str] = field(default_factory=list)
    feature_fields: list[str] = field(default_factory=list)
    qlib_instruments: list[str] = field(default_factory=list)
    fit_start: str = ""
    fit_end: str = ""

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """转发 DataHandlerLP.fetch。"""
        return self.inner.fetch(*args, **kwargs)


def _inject_fit_window(
    processors: list[dict[str, Any]],
    fit_start: str,
    fit_end: str,
) -> list[dict[str, Any]]:
    """为需要 fit 的 processor 注入 fit_start_time / fit_end_time。"""
    out: list[dict[str, Any]] = []
    for step in processors:
        copied = dict(step)
        kwargs = dict(copied.get("kwargs") or {})
        # CSZScoreNorm 等需要 fit 窗口
        kwargs.setdefault("fit_start_time", fit_start)
        kwargs.setdefault("fit_end_time", fit_end)
        copied["kwargs"] = kwargs
        out.append(copied)
    return out


class HandlerBuilder:
    """从 ResearchDatasetSpec 构造 QuantDingerQLibHandler。"""

    def __init__(
        self,
        query: DataQuery,
        *,
        runtime: QlibRuntime,
        materializer: Any,
        registry: ResearchRegistry | None,
        versions: VersionResolver,
        features: FeatureAdapter | None = None,
        labels: LabelAdapter | None = None,
        processors: ProcessorAdapter | None = None,
        enforce_pit_no_fundamental: bool = True,
    ) -> None:
        self._query = query
        self._runtime = runtime
        self._materializer = materializer
        self._registry = registry
        self._versions = versions
        self._features = features or FeatureAdapter()
        self._labels = labels or LabelAdapter()
        self._processors = processors or ProcessorAdapter(registry)
        self._enforce_pit = enforce_pit_no_fundamental

    def build(
        self,
        spec: ResearchDatasetSpec,
        *,
        force_materialize: bool | None = None,
    ) -> QuantDingerQLibHandler:
        """构建 Handler：materialize → activate → DataHandlerLP(feature+label)。"""
        try:
            from qlib.data.dataset.handler import DataHandlerLP
        except ImportError as exc:
            raise QlibAdapterError("pyqlib required for QuantDingerQLibHandler") from exc

        bundle = self._versions.resolve(spec.dataset_ref)
        definition = bundle.handle.definition
        force = (
            force_materialize
            if force_materialize is not None
            else bool(spec.force_materialize)
        )

        # PIT：Handler 路径禁止 fundamental（财务进 Handler 属后续阶段）
        fund_spy: MagicMock | None = None
        original_fundamental = None
        if self._enforce_pit and definition.pit:
            original_fundamental = self._query.fundamental
            fund_spy = MagicMock(side_effect=original_fundamental)
            self._query.fundamental = fund_spy  # type: ignore[method-assign]

        try:
            materialization = self._materializer.materialize(
                spec.dataset_ref, force=force
            )
            self._runtime.activate(materialization.cache_path, kernels=1)

            win_start, win_end = spec.segments.handler_window()
            members = self._query.universe(
                definition.universe_code,
                win_end,
                snapshot_id=definition.snapshot_id,
                universe_version=definition.universe_version,
            )
            if not members:
                raise QlibAdapterError("empty universe for QuantDingerQLibHandler")

            qlib_insts = [to_qlib_instrument(ik).lower() for ik in members]

            raw_feats = list(definition.features) or [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
            ]
            feature_fields = self._features.to_qlib_fields(raw_feats)

            # Label：spec 覆盖 > definition.label > 默认 fwd_ret
            label_def = spec.label or definition.label
            resolved_label, compiled_label = self._labels.resolve(label_def)

            learn_p, infer_p = self._processors.build_handler_processors(bundle.processor)

            fit_start = spec.resolved_fit_start().isoformat()
            fit_end = spec.resolved_fit_end().isoformat()
            # Qlib 0.9：fit_* 进 processor kwargs，而非 DataHandlerLP 构造参数
            learn_p = _inject_fit_window(learn_p, fit_start, fit_end)
            infer_p = _inject_fit_window(infer_p, fit_start, fit_end)

            inner = DataHandlerLP(
                instruments=qlib_insts,
                start_time=win_start.isoformat(),
                end_time=win_end.isoformat(),
                data_loader={
                    "class": "QlibDataLoader",
                    "kwargs": {
                        "config": {
                            "feature": feature_fields,
                            "label": [compiled_label.qlib_expression],
                        },
                    },
                },
                learn_processors=learn_p,
                infer_processors=infer_p,
            )

            if fund_spy is not None and fund_spy.called:
                raise QlibAdapterError(
                    "PIT violation: QuantDingerQLibHandler called DataQuery.fundamental"
                )

            return QuantDingerQLibHandler(
                inner=inner,
                bundle=bundle,
                materialization=materialization,
                label=resolved_label,
                compiled_label=compiled_label,
                instruments=members,
                feature_fields=feature_fields,
                qlib_instruments=qlib_insts,
                fit_start=fit_start,
                fit_end=fit_end,
            )
        finally:
            if original_fundamental is not None:
                self._query.fundamental = original_fundamental  # type: ignore[method-assign]
