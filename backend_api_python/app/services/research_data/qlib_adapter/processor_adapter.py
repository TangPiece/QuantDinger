"""ProcessorAdapter：QuantDinger ProcessorDefinition → Qlib processor kwargs。

Phase 2C：第一批 Dropna / Fillna / Winsorize(RobustZScore) / CSZScore / MinMax；
train/infer 同一 pipeline 定义；需 fit 的 step 由 Handler 注入 train 窗。
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.services.research_data.contracts import ProcessorDefinition
from app.services.research_data.hashing import canonical_json
from app.services.research_data.registry import ResearchRegistry

from .errors import UnsupportedProcessorError, VersionResolveError

# 归一化 step 名 → 支持
_SUPPORTED_STEPS = frozenset(
    {
        "identity",
        "dropna",
        "dropnaprocessor",
        "fillna",
        "winsorize",
        "clip",
        "robustzscore",
        "robustzscorenorm",
        "cszscore",
        "cszscorenorm",
        "minmax",
        "minmaxnorm",
    }
)

# 需要 fit_start_time / fit_end_time 的 Qlib class（禁止 silent 全样本 fit）
_FIT_REQUIRED_CLASSES = frozenset(
    {
        "RobustZScoreNorm",
        "MinMaxNorm",
        "ZScoreNorm",
    }
)


def _step_name(step: dict[str, Any]) -> str:
    """从 pipeline 步骤提取类型名。"""
    for key in ("class", "name", "type", "op"):
        if key in step and step[key]:
            return str(step[key]).strip()
    raise UnsupportedProcessorError(f"processor step missing class/name: {step!r}")


def normalize_step_name(name: str) -> str:
    """小写并去掉下划线，便于白名单比对。"""
    return str(name).strip().lower().replace("_", "")


def compute_pipeline_digest(pipeline: list[dict[str, Any]] | None) -> str:
    """pipeline 内容指纹；空 / None → 'none'。"""
    if not pipeline:
        return "none"
    payload = canonical_json(pipeline)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def qlib_class_needs_fit(qlib_class: str) -> bool:
    """Qlib processor class 是否必须带 train fit 窗。"""
    return str(qlib_class) in _FIT_REQUIRED_CLASSES


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

    def definition_needs_fit(self, processor: ProcessorDefinition | None) -> bool:
        """pipeline 中是否含需 fit 的 step（须经 ResearchDatasetSpec）。"""
        if processor is None:
            return False
        learn, _ = self.build_handler_processors(processor)
        return any(qlib_class_needs_fit(str(s.get("class") or "")) for s in learn)

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
            name = normalize_step_name(_step_name(step))
            if name in ("identity",):
                continue
            if name not in _SUPPORTED_STEPS:
                raise UnsupportedProcessorError(
                    f"unsupported processor step for Phase 2C: {name!r}; "
                    f"allowed=identity, Dropna, Fillna, Winsorize/Clip/RobustZScore, "
                    f"CSZScore, MinMax"
                )
            learn.append(self._to_qlib_processor(step, name))

        # 训练与推理必须同一 Processor Definition
        infer = list(learn)
        return learn, infer

    def _to_qlib_processor(self, step: dict[str, Any], name: str) -> dict[str, Any]:
        """映射到 Qlib processor 配置字典。"""
        kwargs = dict(step.get("kwargs") or {})
        default_fg = {"fields_group": "feature"}

        if name in ("dropna", "dropnaprocessor"):
            return {
                "class": "DropnaProcessor",
                "kwargs": kwargs or default_fg,
            }
        if name in ("fillna",):
            # 默认填 0，可被 kwargs.fill_value 覆盖
            base = {"fields_group": "feature", "fill_value": 0}
            base.update(kwargs)
            return {"class": "Fillna", "kwargs": base}
        if name in ("winsorize", "clip", "robustzscore", "robustzscorenorm"):
            # Qlib 无独立 Winsorize：RobustZScoreNorm + clip_outlier（±3）
            base = {"fields_group": "feature", "clip_outlier": True}
            base.update(kwargs)
            return {"class": "RobustZScoreNorm", "kwargs": base}
        if name in ("cszscore", "cszscorenorm"):
            return {
                "class": "CSZScoreNorm",
                "kwargs": kwargs or default_fg,
            }
        if name in ("minmax", "minmaxnorm"):
            base = {"fields_group": "feature"}
            base.update(kwargs)
            return {"class": "MinMaxNorm", "kwargs": base}
        raise UnsupportedProcessorError(f"unmapped processor step: {name!r}")


def inject_fit_window(
    processors: list[dict[str, Any]],
    fit_start: str,
    fit_end: str,
) -> list[dict[str, Any]]:
    """仅为需要 fit 的 Qlib processor 注入 fit_start_time / fit_end_time。"""
    out: list[dict[str, Any]] = []
    for step in processors:
        copied = dict(step)
        cls = str(copied.get("class") or "")
        if qlib_class_needs_fit(cls):
            kwargs = dict(copied.get("kwargs") or {})
            kwargs.setdefault("fit_start_time", fit_start)
            kwargs.setdefault("fit_end_time", fit_end)
            copied["kwargs"] = kwargs
        out.append(copied)
    return out


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


def builtin_qd_standard_processor() -> ProcessorDefinition:
    """Phase 2C 标准链：Fillna → RobustZScore(clip) → CSZScore。"""
    return ProcessorDefinition(
        code="qd_standard",
        version="1",
        pipeline=[
            {"class": "Fillna", "kwargs": {"fields_group": "feature", "fill_value": 0}},
            {
                "class": "RobustZScoreNorm",
                "kwargs": {"fields_group": "feature", "clip_outlier": True},
            },
            {"class": "CSZScoreNorm", "kwargs": {"fields_group": "feature"}},
        ],
    )
