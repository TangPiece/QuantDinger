"""Stub Training Executor（无 Qlib / ModelTrainer）。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifact_store import ModelArtifactStore
from .prepare_gate import PrepareGateError, assert_prepare_pass, evaluate_prepare_gate
from .protocol import ModelPlatformInject, TrainingRun


class StubExecutorError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        failure_class: str = "SYSTEM_ERROR",
        stage: str = "",
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.stage = stage


def write_stub_sidecars(
    store: ModelArtifactStore,
    run: TrainingRun,
    *,
    metrics: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """写 logs/metrics 本地 stub；返回 (logs_uri, metrics_uri, metrics)."""
    base = store.training_sidecar_dir(training_run_id=run.training_run_id)
    logs_dir = base / "logs"
    metrics_dir = base / "metrics"
    meta_dir = base / "metadata"
    logs_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    stdout = logs_dir / "stdout.log"
    stderr = logs_dir / "stderr.log"
    stdout.write_text(
        f"stub train start {run.training_run_id}\nstatus=RUNNING\n",
        encoding="utf-8",
    )
    stderr.write_text("", encoding="utf-8")

    m = dict(metrics or {})
    m.setdefault("training_loss", 0.12)
    m.setdefault("validation_loss", 0.15)
    m.setdefault("best_iteration", 42)
    m.setdefault("best_score", 0.15)
    m.setdefault("samples", 1000)
    m.setdefault("features", 8)
    m.setdefault(
        "training_duration_sec",
        0.01,
    )
    metrics_path = metrics_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest = {
        "training_run_id": run.training_run_id,
        "dataset_hash": run.dataset_hash,
        "training_config_hash": run.training_config_hash,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    (meta_dir / "training_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return str(stdout.resolve()), str(metrics_path.resolve()), m


def stub_artifact_checksum(run: TrainingRun) -> str:
    payload = f"{run.training_run_id}|{run.training_run_hash}|{run.training_config_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_prepare_stage(
    run: TrainingRun,
    *,
    inject: ModelPlatformInject | None,
) -> None:
    if inject and inject.simulate_fail_at == "PREPARING":
        raise StubExecutorError(
            "inject prepare failure",
            failure_class="DATA_MISSING",
            stage="PREPARING",
        )
    known = inject.known_hashes if inject else None
    reasons = evaluate_prepare_gate(run, known_hashes=known)
    try:
        assert_prepare_pass(reasons)
    except PrepareGateError as exc:
        raise StubExecutorError(
            exc.reason, failure_class=exc.failure_class, stage="PREPARING"
        ) from exc


def run_running_stage(
    store: ModelArtifactStore,
    run: TrainingRun,
    *,
    inject: ModelPlatformInject | None,
) -> tuple[str, str, dict[str, Any]]:
    if inject and inject.simulate_cancel:
        raise StubExecutorError(
            "inject cancel", failure_class="CANCELLED", stage="RUNNING"
        )
    if inject and inject.simulate_fail_at == "RUNNING":
        raise StubExecutorError(
            "inject running failure",
            failure_class="MODEL_ERROR",
            stage="RUNNING",
        )
    return write_stub_sidecars(store, run)


def run_finalizing_stage(
    run: TrainingRun,
    *,
    inject: ModelPlatformInject | None,
) -> str:
    if inject and inject.simulate_fail_at == "FINALIZING":
        raise StubExecutorError(
            "inject finalize failure",
            failure_class="ARTIFACT_ERROR",
            stage="FINALIZING",
        )
    return stub_artifact_checksum(run)


__all__ = [
    "StubExecutorError",
    "run_finalizing_stage",
    "run_prepare_stage",
    "run_running_stage",
    "stub_artifact_checksum",
    "write_stub_sidecars",
]
