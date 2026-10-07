"""ModelArtifact 状态机。"""

from __future__ import annotations

from .protocol import ArtifactStatus


class ArtifactLifecycleError(ValueError):
    pass


_TRANSITIONS: dict[ArtifactStatus, frozenset[ArtifactStatus]] = {
    "CREATING": frozenset({"UPLOADING", "FAILED"}),
    "UPLOADING": frozenset({"VERIFYING", "FAILED"}),
    "VERIFYING": frozenset({"AVAILABLE", "CORRUPTED", "FAILED"}),
    "AVAILABLE": frozenset({"CORRUPTED"}),  # 篡改检测
    "FAILED": frozenset(),
    "CORRUPTED": frozenset(),
}


def assert_artifact_status_transition(
    current: ArtifactStatus, target: ArtifactStatus
) -> None:
    if current == target:
        return
    allowed = _TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ArtifactLifecycleError(
            f"illegal artifact status transition: {current} → {target}"
        )


def is_terminal_artifact_status(status: ArtifactStatus) -> bool:
    return status in ("AVAILABLE", "FAILED", "CORRUPTED")


def is_content_sealed(status: ArtifactStatus) -> bool:
    """AVAILABLE 后内容不可覆盖。"""
    return status == "AVAILABLE"


__all__ = [
    "ArtifactLifecycleError",
    "assert_artifact_status_transition",
    "is_content_sealed",
    "is_terminal_artifact_status",
]
