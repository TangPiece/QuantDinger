"""Compute Planner：按 capability 选择引擎并生成 ComputePlan。"""

from __future__ import annotations

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.factor_lab.hash import compute_factor_hash
from app.services.research_data.factor_lab.types import recommend_layout
from app.services.research_data.registry import ResearchRegistry

from .hash import compute_plan_hash
from .protocol import ComputePlan, PITComputeContext
from .resolver import resolve_dependency_dag

ENGINE_VERSIONS = {
    "polars": "polars_factor@1",
    "quantdinger": "quantdinger_factor@1",
    "duckdb": "duckdb_factor@1",
    "qlib": "qlib_factor@1",
    "level2": "level2_factor@1",
}


class ComputePlanError(ValueError):
    """无法生成合法 ComputePlan。"""


def select_engine(feature: FeatureDefinition) -> str:
    """按定义与依赖能力选择引擎（非硬编码业务因子名）。"""
    deps = feature.dependencies or []
    expr = (feature.expression or "").strip()
    declared = (feature.computation_engine or "quantdinger").lower()

    if declared == "level2" or any(d.startswith("level2:") for d in deps):
        return "level2"
    if declared == "qlib" or "$" in expr or "Ref($" in expr or "Mean($" in expr:
        return "qlib"
    if declared == "duckdb":
        return "duckdb"
    if declared == "polars":
        return "polars"
    # quantdinger 默认走 polars 实现
    return "quantdinger" if declared == "quantdinger" else "polars"


def build_compute_plan(
    feature: FeatureDefinition,
    context: PITComputeContext,
    registry: ResearchRegistry,
) -> ComputePlan:
    """Dependency DAG + 引擎选择 → ComputePlan。"""
    if feature.information_policy == "PIT_SAFE":
        if context.knowledge_time is None:
            raise ComputePlanError("PIT_SAFE requires knowledge_time")
        if not any(
            (d.startswith("fundamental:") for d in (feature.dependencies or []))
        ):
            raise ComputePlanError("PIT_SAFE factor requires fundamental dependency")

    dag = resolve_dependency_dag(feature, registry)
    engine = select_engine(feature)
    # quantdinger 计划字段保留 quantdinger，实际由 Polars 引擎 supports
    fhash = feature.factor_hash or compute_factor_hash(feature)
    layout = recommend_layout(
        factor_type=feature.factor_type,
        n_columns=1,
        information_policy=feature.information_policy,
    )
    schema = feature.schema_version or (
        "factor_daily_wide@1" if layout == "wide" else "factor_daily_long@1"
    )
    eng_ver = feature.engine_version or ENGINE_VERSIONS.get(engine, "unknown@1")
    plan_hash = compute_plan_hash(
        factor_ref=f"{feature.code}@{feature.version}",
        factor_hash=fhash,
        engine=engine,
        engine_version=eng_ver,
        dependency_order=dag.order,
        context=context,
        expression=feature.expression,
        layout=layout,
        schema_version=schema,
        information_policy=feature.information_policy,
    )
    input_hash = context.canonical_dataset_hash or context.snapshot_id
    return ComputePlan(
        factor_ref=f"{feature.code}@{feature.version}",
        factor_hash=fhash,
        plan_hash=plan_hash,
        snapshot_id=context.snapshot_id,
        dataset_hash=input_hash,
        engine=engine,  # type: ignore[arg-type]
        engine_version=eng_ver,
        dependency_order=dag.order,
        frequency=feature.frequency,
        universe_code=context.universe_code or (feature.universe or ""),
        start_date=context.start_date,
        end_date=context.end_date,
        knowledge_time=context.knowledge_time,
        price_policy=context.price_policy,
        processor_ref=context.processor_ref or feature.processor_ref,
        layout=layout,
        schema_version=schema,
        expression=feature.expression,
        information_policy=feature.information_policy,
        metadata={"dag_edges": [list(e) for e in dag.edges]},
    )
