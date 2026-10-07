"""TrainingRun → 不可变 ReproducibilityManifest。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .environment import capture_environment
from .identity import new_repro_manifest_id
from .input_manifest import build_input_manifest
from .protocol import ReproducibilityInject, ReproducibilityManifest
from .seeds import build_seed_bundle


def _meta(run: Any) -> dict[str, Any]:
    return dict(getattr(run, "metadata", None) or {})


def capture_manifest_from_training_run(
    run: Any,
    *,
    artifact: Any | None = None,
    inject: ReproducibilityInject | None = None,
    model_adapter: str = "",
    model_adapter_version: str = "9f4-adapter-1.0.0",
) -> ReproducibilityManifest:
    meta = _meta(run)
    master = int(getattr(run, "random_seed", 0) or 0)
    seeds = build_seed_bundle(master, torch=str(getattr(run, "framework", "")).upper() in ("PYTORCH", "TORCH"))
    env = capture_environment(
        inject=inject,
        ml_framework=str(getattr(run, "framework", "") or ""),
        qlib_version=str(meta.get("qlib_version") or ""),
    )
    code_commit = ""
    if inject and inject.code_commit:
        code_commit = inject.code_commit
    else:
        code_commit = str(meta.get("code_commit") or getattr(run, "code_version", "") or "")

    input_man = build_input_manifest(
        dataset_hash=str(getattr(run, "dataset_hash", "") or ""),
        snapshot_id=str(getattr(run, "snapshot_id", "") or ""),
        partitions=meta.get("partitions"),
        schema_hash=str(meta.get("schema_hash") or ""),
        row_count=int(meta.get("row_count") or 0),
        min_event_time=str(getattr(run, "train_start", "") or ""),
        max_event_time=str(getattr(run, "train_end", "") or ""),
        inject=inject,
    )

    det_req = True
    det_sup = True
    det_en = True
    if inject:
        if inject.deterministic_requested is not None:
            det_req = inject.deterministic_requested
        if inject.deterministic_supported is not None:
            det_sup = inject.deterministic_supported
        if inject.deterministic_enabled is not None:
            det_en = inject.deterministic_enabled
        if inject.force_non_deterministic:
            det_en = False
            det_sup = False

    art_id = ""
    art_cs = ""
    if artifact is not None:
        art_id = str(getattr(artifact, "artifact_id", "") or "")
        art_cs = str(getattr(artifact, "checksum", "") or "")
    if inject and inject.artifact_checksum_original:
        art_cs = inject.artifact_checksum_original

    metrics = dict(getattr(run, "metrics", None) or {})
    if inject and inject.metrics_original:
        metrics = dict(inject.metrics_original)

    now = datetime.now(timezone.utc)
    return ReproducibilityManifest(
        repro_manifest_id=new_repro_manifest_id(),
        training_run_id=str(getattr(run, "training_run_id", "") or ""),
        model_id=str(getattr(run, "model_id", "") or ""),
        model_version_id=str(getattr(run, "model_version_id", "") or ""),
        dataset_hash=str(getattr(run, "dataset_hash", "") or ""),
        snapshot_id=str(getattr(run, "snapshot_id", "") or ""),
        feature_set_hash=str(getattr(run, "feature_set_hash", "") or ""),
        factor_portfolio_hash=str(getattr(run, "factor_portfolio_hash", "") or ""),
        label_hash=str(getattr(run, "label_hash", "") or ""),
        processor_version=str(getattr(run, "processor_version", "") or ""),
        training_config_hash=str(getattr(run, "training_config_hash", "") or ""),
        hyperparameter_hash=str(getattr(run, "hyperparameter_hash", "") or ""),
        model_adapter=model_adapter
        or str(meta.get("model_adapter") or getattr(run, "framework", "") or "stub"),
        model_adapter_version=model_adapter_version
        or str(meta.get("model_adapter_version") or "9f4-adapter-1.0.0"),
        framework=str(getattr(run, "framework", "") or ""),
        framework_version=str(getattr(run, "framework_version", "") or ""),
        code_version=str(getattr(run, "code_version", "") or ""),
        code_commit=code_commit,
        environment_hash=env.environment_hash,
        dependency_lock_hash=env.dependency_lock_hash,
        runtime_version=env.python_version,
        os_version=f"{env.os_name} {env.os_version}".strip(),
        container_image_digest=env.container_image_digest,
        random_seed=master,
        seeds=seeds,
        resource_config=dict(getattr(run, "resource_config", None) or {}),
        deterministic_requested=det_req,
        deterministic_supported=det_sup,
        deterministic_enabled=det_en,
        input_manifest=input_man,
        environment=env,
        artifact_id=art_id,
        artifact_checksum=art_cs,
        metrics_snapshot=metrics,
        immutable=True,
        created_at=now,
        metadata={"purpose": "capture"},
    )


__all__ = ["capture_manifest_from_training_run"]
