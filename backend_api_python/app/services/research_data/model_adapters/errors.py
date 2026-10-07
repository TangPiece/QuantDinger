"""Adapter 错误 → TrainingRun failure_class（不泄漏 Qlib 异常到 API）。"""

from __future__ import annotations


class ModelAdapterError(RuntimeError):
    """Adapter 层失败；带 failure_class / stage。"""

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


def map_exception(exc: BaseException, *, stage: str = "") -> ModelAdapterError:
    """将底层异常映射为 ModelAdapterError。"""
    if isinstance(exc, ModelAdapterError):
        return exc
    name = type(exc).__name__
    msg = str(exc) or name
    lower = msg.lower()
    if "not found" in lower or "missing" in lower or "no such" in lower:
        return ModelAdapterError(msg, failure_class="DATA_MISSING", stage=stage)
    if "config" in lower or "invalid" in lower or "validation" in lower:
        return ModelAdapterError(msg, failure_class="CONFIG_ERROR", stage=stage)
    if "artifact" in lower or "checksum" in lower or "write" in lower:
        return ModelAdapterError(msg, failure_class="ARTIFACT_ERROR", stage=stage)
    if "timeout" in lower:
        return ModelAdapterError(msg, failure_class="TIMEOUT", stage=stage)
    if "resource" in lower or "memory" in lower or "omp" in lower:
        return ModelAdapterError(msg, failure_class="RESOURCE_ERROR", stage=stage)
    if stage == "PREPARING":
        return ModelAdapterError(msg, failure_class="DATA_ERROR", stage=stage)
    if stage == "FINALIZING":
        return ModelAdapterError(msg, failure_class="ARTIFACT_ERROR", stage=stage)
    return ModelAdapterError(msg, failure_class="MODEL_ERROR", stage=stage or "RUNNING")


__all__ = ["ModelAdapterError", "map_exception"]
