"""ModelVersion 血缘校验（正式创建路径）。"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .protocol import ModelArtifact, ModelVersion, ModelVersionSpec, TrainingRun

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")

REQUIRED_VERSION_FIELDS = (
    "dataset_hash",
    "snapshot_id",
    "feature_set_id",
    "feature_set_hash",
    "label_hash",
    "processor_version",
    "training_run_id",
)


class LineageValidationError(ValueError):
    pass


def is_sha256_hex(value: str) -> bool:
    return bool(value and _HEX64.match(str(value).strip()))


def assert_checksum(checksum: str, *, expected: str = "") -> None:
    cs = str(checksum or "").strip()
    if not is_sha256_hex(cs):
        raise LineageValidationError("artifact checksum must be 64-char hex sha256")
    if expected and str(expected).strip().lower() != cs.lower():
        raise LineageValidationError("artifact checksum mismatch vs expected_checksum")


def validate_lineage_for_version(
    *,
    spec: ModelVersionSpec,
    training_run: TrainingRun,
    artifact: ModelArtifact | None,
    model_config_hash: str,
    inject: Mapping[str, Any] | None = None,
) -> list[str]:
    """返回 reasons；空列表 = PASS。正式路径要求非空关键血缘。"""
    reasons: list[str] = []
    if training_run.status not in ("SUCCEEDED", "FINALIZING"):
        reasons.append(f"training_run_status_{training_run.status}")
    if not (training_run.training_run_id or "").strip():
        reasons.append("training_run_id_missing")

    for field in REQUIRED_VERSION_FIELDS:
        val = getattr(spec, field, "") if field != "training_run_id" else (
            spec.training_run_id or training_run.training_run_id
        )
        if field == "training_run_id":
            val = spec.training_run_id or training_run.training_run_id
        else:
            val = getattr(spec, field, "")
        if not str(val or "").strip():
            reasons.append(f"{field}_missing")

    if not str(model_config_hash or "").strip():
        reasons.append("model_config_hash_missing")

    # hash 字段格式（允许非 sha 的 snapshot_id / processor_version / feature_set_id）
    for field in ("dataset_hash", "feature_set_hash", "label_hash"):
        val = str(getattr(spec, field, "") or "")
        if val and not is_sha256_hex(val):
            reasons.append(f"{field}_not_sha256")

    # portfolio 成对
    pid = str(spec.factor_portfolio_id or "").strip()
    pver = str(spec.factor_portfolio_version or "").strip()
    if (pid and not pver) or (pver and not pid):
        reasons.append("factor_portfolio_id_version_pair_required")

    # 与 TrainingRun 对齐
    if spec.dataset_hash and training_run.dataset_hash:
        if spec.dataset_hash != training_run.dataset_hash:
            reasons.append("dataset_hash_mismatch_vs_training_run")
    if spec.feature_set_hash and training_run.feature_set_hash:
        if spec.feature_set_hash != training_run.feature_set_hash:
            reasons.append("feature_set_hash_mismatch_vs_training_run")

    if artifact is None and not str(spec.artifact_id or "").strip():
        reasons.append("artifact_id_missing")
    if artifact is not None:
        try:
            assert_checksum(artifact.checksum)
        except LineageValidationError as exc:
            reasons.append(str(exc))

    # optional known-hash inject / service stubs
    known = {}
    if inject:
        known = dict(inject.get("known_hashes") or {})
    if known.get("dataset_hash") and spec.dataset_hash:
        if known["dataset_hash"] != spec.dataset_hash:
            reasons.append("dataset_hash_not_found")
    if known.get("feature_set_hash") and spec.feature_set_hash:
        if known["feature_set_hash"] != spec.feature_set_hash:
            reasons.append("feature_set_hash_not_found")
    if known.get("label_hash") and spec.label_hash:
        if known["label_hash"] != spec.label_hash:
            reasons.append("label_hash_not_found")
    if known.get("snapshot_id") and spec.snapshot_id:
        if known["snapshot_id"] != spec.snapshot_id:
            reasons.append("snapshot_id_not_found")
    if known.get("factor_portfolio_hash") and training_run.factor_portfolio_hash:
        if known["factor_portfolio_hash"] != training_run.factor_portfolio_hash:
            reasons.append("factor_portfolio_hash_not_found")

    return reasons


def assert_lineage_pass(reasons: list[str]) -> None:
    if reasons:
        raise LineageValidationError("; ".join(reasons))


def lineage_view(
    version: ModelVersion,
    *,
    training_run: TrainingRun | None = None,
    artifact: ModelArtifact | None = None,
    repro_path: str = "",
) -> dict[str, Any]:
    return {
        "model_version_id": version.model_version_id,
        "model_id": version.model_id,
        "model_code": version.model_code,
        "version": version.version,
        "lifecycle": version.lifecycle,
        "version_content_hash": version.version_content_hash,
        "dataset_hash": version.dataset_hash,
        "snapshot_id": version.snapshot_id,
        "feature_set_id": version.feature_set_id,
        "feature_set_hash": version.feature_set_hash,
        "factor_portfolio_id": version.factor_portfolio_id,
        "factor_portfolio_version": version.factor_portfolio_version,
        "factor_portfolio_hash": (version.metadata or {}).get("factor_portfolio_hash", ""),
        "label_id": version.label_id,
        "label_hash": version.label_hash,
        "processor_version": version.processor_version,
        "model_config_hash": version.model_config_hash,
        "hyperparameter_hash": version.hyperparameter_hash,
        "framework": version.framework,
        "framework_version": version.framework_version,
        "code_version": version.code_version,
        "environment_hash": version.environment_hash,
        "random_seed": version.random_seed,
        "training_run_id": version.training_run_id,
        "artifact_id": version.artifact_id,
        "training_run": training_run.model_dump(mode="json") if training_run else None,
        "artifact": artifact.model_dump(mode="json") if artifact else None,
        "repro_manifest_uri": repro_path,
    }


def full_lineage_view(
    *,
    model: Any | None,
    version: ModelVersion,
    training_run: TrainingRun | None = None,
    artifact: ModelArtifact | None = None,
    tip_repro: Mapping[str, Any] | None = None,
    full_repro_manifest: Mapping[str, Any] | None = None,
    evaluation_runs: list[Any] | None = None,
    approvals: list[Any] | None = None,
    activations: list[Any] | None = None,
    reproducibility_runs: list[Any] | None = None,
    experiment_refs: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """9F-9：一键完整血缘树（Service 契约；无 Flask）。"""

    def _dump(obj: Any) -> Any:
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if isinstance(obj, Mapping):
            return dict(obj)
        return obj

    tip = lineage_view(
        version,
        training_run=training_run,
        artifact=artifact,
        repro_path=str((tip_repro or {}).get("repro_manifest_uri") or ""),
    )
    return {
        "schema": "model_full_lineage@1",
        "model": _dump(model),
        "model_version": tip,
        "training_run": _dump(training_run),
        "artifact": _dump(artifact),
        "repro_tip": dict(tip_repro) if tip_repro else None,
        "reproducibility_manifest": dict(full_repro_manifest)
        if full_repro_manifest
        else None,
        "evaluation_runs": [_dump(r) for r in (evaluation_runs or [])],
        "approvals": [_dump(a) for a in (approvals or [])],
        "activation_records": [_dump(a) for a in (activations or [])],
        "reproducibility_runs": [_dump(r) for r in (reproducibility_runs or [])],
        "experiment_refs": [dict(x) for x in (experiment_refs or [])],
        "boundaries": {
            "model_active_ne_strategy_live": True,
            "http_deferred_to_9h": True,
        },
    }


__all__ = [
    "LineageValidationError",
    "REQUIRED_VERSION_FIELDS",
    "assert_checksum",
    "assert_lineage_pass",
    "full_lineage_view",
    "is_sha256_hex",
    "lineage_view",
    "validate_lineage_for_version",
]
