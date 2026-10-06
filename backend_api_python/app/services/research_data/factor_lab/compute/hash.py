"""ComputePlan / Result Dataset 内容哈希。"""

from __future__ import annotations

import hashlib
from datetime import datetime

from app.services.research_data.hashing import canonical_json

from .protocol import ComputePlan, PITComputeContext


def _kt_iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def compute_plan_hash(
    *,
    factor_ref: str,
    factor_hash: str,
    engine: str,
    engine_version: str,
    dependency_order: list[str],
    context: PITComputeContext,
    expression: str,
    layout: str,
    schema_version: str,
    information_policy: str,
) -> str:
    """计划指纹（选择引擎后、执行前）。"""
    pp = context.price_policy.model_dump(mode="json")
    payload = {
        "factor_ref": factor_ref,
        "factor_hash": factor_hash,
        "engine": engine,
        "engine_version": engine_version or "",
        "dependency_order": list(dependency_order),
        "snapshot_id": context.snapshot_id,
        "input_dataset_hash": context.canonical_dataset_hash or "",
        "start": context.start_date,
        "end": context.end_date,
        "knowledge_time": _kt_iso(context.knowledge_time),
        "universe": context.universe_code or "",
        "price_policy": pp,
        "processor_ref": context.processor_ref or "",
        "expression": expression,
        "layout": layout,
        "schema_version": schema_version,
        "information_policy": information_policy,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_result_dataset_hash(plan: ComputePlan) -> str:
    """结果 dataset_hash：同输入重复计算必须相同。"""
    payload = {
        "factor_hash": plan.factor_hash,
        "snapshot_id": plan.snapshot_id,
        "input_dataset_hash": plan.dataset_hash,
        "dependency_order": list(plan.dependency_order),
        "processor_ref": plan.processor_ref or "",
        "price_policy": plan.price_policy.model_dump(mode="json"),
        "engine": plan.engine,
        "engine_version": plan.engine_version or "",
        "schema_version": plan.schema_version,
        "start": plan.start_date,
        "end": plan.end_date,
        "knowledge_time": _kt_iso(plan.knowledge_time),
        "layout": plan.layout,
        "plan_hash": plan.plan_hash,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
