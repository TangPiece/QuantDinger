"""EvaluationRun 血缘：Factor build → Dataset → Policy。"""

from __future__ import annotations

from typing import Any, Protocol

from .protocol import EvaluationRunIndex, LineageNode


class _RegistryLike(Protocol):
    def get_feature(self, feature_ref: str) -> Any: ...

    def get_dataset(self, dataset_ref: str) -> Any: ...


def build_evaluation_lineage(
    registry: _RegistryLike,
    run: EvaluationRunIndex,
) -> LineageNode:
    root = LineageNode(
        ref=run.evaluation_id,
        kind="EVALUATION_RUN",
        hash_value=run.run_content_hash,
        children=[
            LineageNode(
                ref=run.factor_ref,
                kind="FACTOR",
                hash_value=run.factor_hash,
            ),
            LineageNode(
                ref=run.dataset_ref,
                kind="DATASET",
                hash_value=run.dataset_hash,
            ),
            LineageNode(
                ref=run.policy_id,
                kind="EVALUATION_POLICY",
                hash_value=run.policy_content_hash,
            ),
        ],
    )
    if run.evaluation_hash:
        root.children.append(
            LineageNode(ref=run.evaluation_hash, kind="EVALUATION_DATASET")
        )
    if run.metric_hash:
        root.children.append(LineageNode(ref=run.metric_hash, kind="METRIC"))
    if run.group_evaluation_hash:
        root.children.append(
            LineageNode(ref=run.group_evaluation_hash, kind="GROUP_EVAL")
        )
    if run.stability_hash:
        root.children.append(LineageNode(ref=run.stability_hash, kind="STABILITY"))
    return root


def list_runs_by_factor(registry: Any, factor_hash: str) -> list[str]:
    """registry 侧索引（可选）；主路径为 artifact 扫描。"""
    target = str(factor_hash or "").strip()
    if not target or not hasattr(registry, "_read"):
        return []
    data = registry._read()  # type: ignore[attr-defined]
    out: list[str] = []
    for _eid, raw in (data.get("evaluation_runs") or {}).items():
        if str(raw.get("factor_hash") or "") == target:
            out.append(str(raw.get("evaluation_id") or _eid))
    return sorted(out)


__all__ = ["build_evaluation_lineage", "list_runs_by_factor"]
