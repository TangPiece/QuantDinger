"""evaluation_hash：钉住 FactorDataset + Spec + Universe + Return。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import EvaluationPlan, EvaluationSpec


def normalize_spec_payload(spec: EvaluationSpec, *, factor_dataset_hash: str) -> dict:
    """规范化 hash 输入（不含 runtime metadata）。"""
    return {
        "factor_dataset_id": spec.factor_dataset_id,
        "factor_dataset_hash": factor_dataset_hash,
        "universe_code": spec.universe_code or "",
        "universe_version": spec.universe_version or "",
        "snapshot_id": spec.snapshot_id,
        "start_date": spec.start_date,
        "end_date": spec.end_date,
        "frequency": spec.frequency,
        "return_spec": spec.return_spec.model_dump(mode="json"),
        "price_policy": spec.price_policy.model_dump(mode="json"),
        "missing_data_policy": spec.missing_data_policy.model_dump(
            mode="json", by_alias=True
        ),
        "mode": spec.mode,
        "evaluator_version": spec.evaluator_version,
        "calendar_version": spec.calendar_version,
    }


def compute_evaluation_hash(
    spec: EvaluationSpec, *, factor_dataset_hash: str
) -> str:
    """稳定 evaluation_hash。"""
    payload = normalize_spec_payload(spec, factor_dataset_hash=factor_dataset_hash)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def plan_hash_payload(plan: EvaluationPlan) -> dict:
    """Plan 侧可复现摘要。"""
    return {
        "evaluation_hash": plan.evaluation_hash,
        "factor_dataset_hash": plan.factor_dataset_hash,
        "snapshot_id": plan.snapshot_id,
        "universe_code": plan.universe_code,
        "universe_version": plan.universe_version,
        "return_spec": plan.return_spec.model_dump(mode="json"),
        "price_policy": plan.price_policy.model_dump(mode="json"),
        "mode": plan.mode,
        "evaluator_version": plan.evaluator_version,
        "calendar_version": plan.calendar_version,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
    }
