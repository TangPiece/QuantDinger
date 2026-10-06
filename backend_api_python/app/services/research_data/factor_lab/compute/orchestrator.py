"""FactorComputeService：Definition → Plan → Engine → Dataset。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import FactorDatasetRecord, FeatureDefinition
from app.services.research_data.data_query import DataQuery
from app.services.research_data.factor_lab.artifact_store import FactorDatasetArtifactStore
from app.services.research_data.factor_lab.hash import compute_factor_hash
from app.services.research_data.factor_lab.immutability import ensure_factor_hash
from app.services.research_data.registry import ResearchRegistry

from .engines import (
    DuckDBFactorEngine,
    Level2FactorEngine,
    PolarsFactorEngine,
    QlibFactorEngine,
    QuantDingerFactorEngine,
)
from .planner import build_compute_plan
from .protocol import ComputePlan, FactorFrame, PITComputeContext
from .writers import FactorDatasetWriter


class FactorComputeError(RuntimeError):
    """因子计算失败。"""


@dataclass
class ComputeResult:
    """端到端计算结果。"""

    plan: ComputePlan
    frame: FactorFrame
    record: FactorDatasetRecord


class FactorComputeService:
    """编排 Dependency → Plan → Engine → Writer。"""

    def __init__(
        self,
        query: DataQuery,
        registry: ResearchRegistry,
        store: CanonicalStore,
        *,
        artifact_store: FactorDatasetArtifactStore | None = None,
    ) -> None:
        self._query = query
        self._registry = registry
        self._writer = FactorDatasetWriter(
            store, registry, artifact_store=artifact_store
        )
        self._engines = [
            Level2FactorEngine(),
            QlibFactorEngine(),
            DuckDBFactorEngine(),
            QuantDingerFactorEngine(),
            PolarsFactorEngine(),
        ]

    def run(
        self,
        factor_ref: str,
        context: PITComputeContext,
        *,
        metadata: dict[str, Any] | None = None,
        feature: FeatureDefinition | None = None,
    ) -> ComputeResult:
        """执行完整计算流水线。"""
        feat = feature or self._registry.get_feature(factor_ref)
        feat = ensure_factor_hash(feat)
        feat = feat.model_copy(update={"factor_hash": compute_factor_hash(feat)})
        plan = build_compute_plan(feat, context, self._registry)
        if metadata:
            plan = plan.model_copy(
                update={"metadata": {**(plan.metadata or {}), **metadata}}
            )
        engine = self._pick_engine(plan, feat)
        frame = engine.compute(plan, query=self._query, registry=self._registry)
        record = self._writer.write(feat, plan, frame)
        return ComputeResult(plan=plan, frame=frame, record=record)

    def plan_only(
        self, factor_ref: str, context: PITComputeContext
    ) -> ComputePlan:
        """仅生成 ComputePlan（测试/校验）。"""
        feat = self._registry.get_feature(factor_ref)
        feat = ensure_factor_hash(feat)
        return build_compute_plan(feat, context, self._registry)

    def _pick_engine(self, plan: ComputePlan, feature: FeatureDefinition):
        for eng in self._engines:
            if eng.supports(feature, plan):
                return eng
        raise FactorComputeError(f"no engine supports plan.engine={plan.engine!r}")
