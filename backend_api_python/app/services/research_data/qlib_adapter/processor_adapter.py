"""ProcessorAdapter：QuantDinger ProcessorDefinition → Qlib processor kwargs。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import ProcessorDefinition
from app.services.research_data.registry import ResearchRegistry

from .errors import UnsupportedProcessorError, VersionResolveError

# Phase 2A 白名单：step 名（小写）→ 构造器
_SUPPORTED_STEPS = frozenset({"identity", "dropna", "dropnaprocessor", "cszscore", "cszscorenorm"})


def _step_name(step: dict[str, Any]) -> str:
    """从 pipeline 步骤提取类型名。"""
    for key in ("class", "name", "type", "op"):
        if key in step and step[key]:
            return str(step[key]).strip()
    raise UnsupportedProcessorError(f"processor step missing class/name: {step!r}")


class ProcessorAdapter:
    """解析 ProcessorDefinition，生成 DataHandlerLP 的 learn/infer processors。"""

    def __init__(self, registry: ResearchRegistry | None = None) -> None:
        self._registry = registry

    def resolve_definition(self, processor_ref: str | None) -> ProcessorDefinition | None:
        """加载 code@version；None / none → 恒等。"""
        ref = (processor_ref or "").strip()
        if not ref or ref.lower() == "none":
            return None
        if self._registry is None:
            raise VersionResolveError("registry required to load processor")
        return self._registry.get_processor(ref)

    def build_handler_processors(
        self,
        processor: ProcessorDefinition | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """返回 (learn_processors, infer_processors)；训练/推理共用同一配置。"""
        if processor is None:
            return [], []

        learn: list[dict[str, Any]] = []
        for step in processor.pipeline:
            if not isinstance(step, dict):
                raise UnsupportedProcessorError(f"pipeline step must be dict, got {step!r}")
            name = _step_name(step).lower().replace("_", "")
            if name in ("identity",):
                continue
            if name not in _SUPPORTED_STEPS:
                raise UnsupportedProcessorError(
                    f"unsupported processor step for Phase 2A: {name!r}; "
                    f"allowed=identity, DropnaProcessor, CSZScoreNorm"
                )
            learn.append(self._to_qlib_processor(step, name))

        # 训练与推理必须同一 Processor Definition
        infer = list(learn)
        return learn, infer

    def _to_qlib_processor(self, step: dict[str, Any], name: str) -> dict[str, Any]:
        """映射到 Qlib processor 配置字典。"""
        kwargs = dict(step.get("kwargs") or {})
        if name in ("dropna", "dropnaprocessor"):
            return {
                "class": "DropnaProcessor",
                "kwargs": kwargs or {"fields_group": "feature"},
            }
        if name in ("cszscore", "cszscorenorm"):
            return {
                "class": "CSZScoreNorm",
                "kwargs": kwargs or {"fields_group": "feature"},
            }
        raise UnsupportedProcessorError(f"unmapped processor step: {name!r}")


def builtin_identity_processor() -> ProcessorDefinition:
    """测试用恒等 Processor。"""
    return ProcessorDefinition(code="identity", version="1", pipeline=[])


def builtin_cs_zscore_processor() -> ProcessorDefinition:
    """测试用截面 ZScore Processor。"""
    return ProcessorDefinition(
        code="cs_zscore",
        version="1",
        pipeline=[{"class": "CSZScoreNorm", "kwargs": {"fields_group": "feature"}}],
    )
