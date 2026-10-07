"""Training Executor：stub（默认）或 qlib（经 model_adapters 门面）。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


@dataclass
class RunningStageResult:
    logs_uri: str
    metrics_uri: str
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_uri: str = ""
    checksum: str = ""
    file_size: int = 0
    framework: str = ""
    framework_version: str = ""
    candidate_metadata: dict[str, Any] = field(default_factory=dict)


def resolve_executor_kind(run: TrainingRun) -> str:
    rc = dict(run.resource_config or {})
    kind = str(rc.get("executor") or "local").strip().lower()
    if kind in ("", "local", "stub"):
        return "stub"
    if kind in ("qlib", "lightgbm"):
        return "qlib"
    return kind


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
    m.setdefault("training_duration_sec", 0.01)
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


def write_train_sidecars(
    store: ModelArtifactStore,
    run: TrainingRun,
    *,
    metrics: dict[str, Any] | None = None,
    extra_log: str = "",
) -> tuple[str, str, dict[str, Any]]:
    base = store.training_sidecar_dir(training_run_id=run.training_run_id)
    logs_dir = base / "logs"
    metrics_dir = base / "metrics"
    logs_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    stdout = logs_dir / "stdout.log"
    stdout.write_text(
        f"qlib train start {run.training_run_id}\n{extra_log}\n",
        encoding="utf-8",
    )
    m = dict(metrics or {})
    metrics_path = metrics_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True),
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
    data_query: Any | None = None,
    adapter: Any | None = None,
    ctx: Any | None = None,
) -> None:
    if inject and inject.simulate_fail_at == "PREPARING":
        raise StubExecutorError(
            "inject prepare failure",
            failure_class="DATA_MISSING",
            stage="PREPARING",
        )
    kind = resolve_executor_kind(run)
    known = inject.known_hashes if inject else None
    skip_ref = bool(inject.skip_dataset_ref_check) if inject else False
    reasons = evaluate_prepare_gate(
        run,
        known_hashes=known,
        require_dataset_ref=(kind == "qlib"),
        data_query=data_query,
        skip_dataset_ref_check=skip_ref,
    )
    try:
        assert_prepare_pass(reasons)
    except PrepareGateError as exc:
        raise StubExecutorError(
            exc.reason, failure_class=exc.failure_class, stage="PREPARING"
        ) from exc

    if kind == "qlib" and adapter is not None and ctx is not None:
        try:
            adapter.prepare(ctx)
        except Exception as exc:
            failure_class = getattr(exc, "failure_class", "DATA_ERROR")
            raise StubExecutorError(
                str(exc), failure_class=failure_class, stage="PREPARING"
            ) from exc


def run_running_stage(
    store: ModelArtifactStore,
    run: TrainingRun,
    *,
    inject: ModelPlatformInject | None,
    adapter: Any | None = None,
    ctx: Any | None = None,
) -> RunningStageResult:
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
    kind = resolve_executor_kind(run)
    if kind != "qlib":
        logs_uri, metrics_uri, metrics = write_stub_sidecars(store, run)
        return RunningStageResult(
            logs_uri=logs_uri,
            metrics_uri=metrics_uri,
            metrics=metrics,
        )

    if adapter is None or ctx is None:
        raise StubExecutorError(
            "qlib executor requires adapter and TrainingContext",
            failure_class="RESOURCE_ERROR",
            stage="RUNNING",
        )
    try:
        candidate = adapter.train(ctx)
    except Exception as exc:
        failure_class = getattr(exc, "failure_class", "MODEL_ERROR")
        raise StubExecutorError(
            str(exc), failure_class=failure_class, stage="RUNNING"
        ) from exc

    logs_uri, metrics_uri, metrics = write_train_sidecars(
        store,
        run,
        metrics=dict(candidate.metrics or {}),
        extra_log=f"checksum={candidate.checksum}\nuri={candidate.artifact_uri}",
    )
    return RunningStageResult(
        logs_uri=logs_uri,
        metrics_uri=metrics_uri,
        metrics=metrics,
        artifact_uri=candidate.artifact_uri,
        checksum=candidate.checksum,
        file_size=int(candidate.file_size or 0),
        framework=candidate.framework or run.framework or "LIGHTGBM",
        framework_version=candidate.framework_version or run.framework_version,
        candidate_metadata=dict(candidate.model_metadata or {}),
    )


def run_finalizing_stage(
    run: TrainingRun,
    *,
    inject: ModelPlatformInject | None,
    running: RunningStageResult | None = None,
) -> str:
    if inject and inject.simulate_fail_at == "FINALIZING":
        raise StubExecutorError(
            "inject finalize failure",
            failure_class="ARTIFACT_ERROR",
            stage="FINALIZING",
        )
    if running and running.checksum:
        return running.checksum
    return stub_artifact_checksum(run)


__all__ = [
    "RunningStageResult",
    "StubExecutorError",
    "resolve_executor_kind",
    "run_finalizing_stage",
    "run_prepare_stage",
    "run_running_stage",
    "stub_artifact_checksum",
    "write_stub_sidecars",
    "write_train_sidecars",
]
