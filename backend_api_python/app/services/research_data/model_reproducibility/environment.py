"""EnvironmentFingerprint 捕获。"""

from __future__ import annotations

import platform
import sys
from typing import Any, Mapping

from .hashing import compute_dependency_lock_hash, compute_environment_hash
from .protocol import EnvironmentFingerprint, ReproducibilityInject


def default_dependency_lock(
    *,
    inject: ReproducibilityInject | None = None,
) -> dict[str, Any]:
    if inject and inject.dependency_lock:
        return dict(inject.dependency_lock)
    return {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "packages": dict(inject.package_versions) if inject and inject.package_versions else {},
        "engine_versions": {"model_reproducibility": "qd_model_reproducibility@1"},
    }


def capture_environment(
    *,
    inject: ReproducibilityInject | None = None,
    ml_framework: str = "",
    qlib_version: str = "",
) -> EnvironmentFingerprint:
    lock = default_dependency_lock(inject=inject)
    packages = dict(lock.get("packages") or {})
    if inject and inject.package_versions:
        packages.update(inject.package_versions)
    digest = ""
    if inject and inject.container_image_digest:
        digest = inject.container_image_digest
    fp = EnvironmentFingerprint(
        python_version=str(lock.get("python_version") or platform.python_version()),
        os_name=platform.system(),
        os_version=platform.release(),
        architecture=platform.machine(),
        cpu=platform.processor() or platform.machine(),
        gpu="",
        cuda="",
        cudnn="",
        qlib_version=qlib_version,
        ml_framework=ml_framework,
        package_versions=packages,
        environment_variables={},
        container_image_digest=digest,
        dependency_lock=lock,
        dependency_lock_hash=compute_dependency_lock_hash(lock),
    )
    env_hash = compute_environment_hash(fp.model_dump(mode="json"))
    return fp.model_copy(update={"environment_hash": env_hash})


def fingerprint_from_mapping(data: Mapping[str, Any]) -> EnvironmentFingerprint:
    return EnvironmentFingerprint.model_validate(dict(data))


__all__ = [
    "capture_environment",
    "default_dependency_lock",
    "fingerprint_from_mapping",
]
