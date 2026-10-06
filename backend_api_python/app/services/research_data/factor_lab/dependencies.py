"""Factor Dependency 解析与校验。"""

from __future__ import annotations

from typing import Sequence

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.registry import ResearchRegistry

from .models import FactorDependency
from .types import DEPENDENCY_TYPES


class FactorDependencyError(ValueError):
    """依赖非法。"""


def parse_dependency(raw: str) -> FactorDependency:
    """解析 ``type:code`` 或纯 code（默认 other）。

    示例：``market:CNStock``、``factor:momentum_20d@1.0.0``、``fundamental:roe``。
    """
    text = str(raw or "").strip()
    if not text:
        raise FactorDependencyError("empty dependency")
    if ":" in text:
        dtype, code = text.split(":", 1)
        dtype = dtype.strip().lower()
        code = code.strip()
    else:
        dtype, code = "other", text
    if dtype not in DEPENDENCY_TYPES:
        raise FactorDependencyError(
            f"unsupported dependency_type={dtype!r}; allow={sorted(DEPENDENCY_TYPES)}"
        )
    if not code:
        raise FactorDependencyError("empty dependency_code")
    return FactorDependency(dependency_type=dtype, dependency_code=code)


def parse_dependencies(raw_list: Sequence[str]) -> list[FactorDependency]:
    """批量解析。"""
    return [parse_dependency(r) for r in raw_list]


def format_dependency(dep: FactorDependency) -> str:
    """标准化为 ``type:code`` 字符串。"""
    return f"{dep.dependency_type}:{dep.dependency_code}"


def validate_dependencies(
    feature: FeatureDefinition,
    registry: ResearchRegistry | None = None,
    *,
    check_cycles: bool = True,
) -> list[FactorDependency]:
    """校验依赖类型；factor 类型须可解析；可选禁环。"""
    deps = parse_dependencies(feature.dependencies or [])
    if registry is not None:
        for d in deps:
            if d.dependency_type == "factor":
                try:
                    registry.get_feature(d.dependency_code)
                except Exception as exc:
                    raise FactorDependencyError(
                        f"factor dependency not found: {d.dependency_code!r}"
                    ) from exc
        if check_cycles:
            _assert_no_cycle(feature, registry, deps)
    return deps


def _assert_no_cycle(
    feature: FeatureDefinition,
    registry: ResearchRegistry,
    deps: list[FactorDependency],
) -> None:
    """浅层 DFS：禁止 factor 依赖环。"""
    self_ref = f"{feature.code}@{feature.version}"
    visiting: set[str] = {self_ref}

    def walk(ref: str) -> None:
        try:
            child = registry.get_feature(ref)
        except Exception:
            return
        for raw in child.dependencies or []:
            d = parse_dependency(raw)
            if d.dependency_type != "factor":
                continue
            if d.dependency_code in visiting:
                raise FactorDependencyError(
                    f"dependency cycle involving {d.dependency_code!r}"
                )
            visiting.add(d.dependency_code)
            walk(d.dependency_code)
            visiting.discard(d.dependency_code)

    for d in deps:
        if d.dependency_type != "factor":
            continue
        if d.dependency_code == self_ref:
            raise FactorDependencyError(f"self dependency: {self_ref}")
        visiting.add(d.dependency_code)
        walk(d.dependency_code)
        visiting.discard(d.dependency_code)


def validate_for_backtest(feature: FeatureDefinition) -> bool:
    """正式回测门禁：UNKNOWN 禁止；PIT_SAFE 须含 fundamental 依赖。"""
    if feature.information_policy == "UNKNOWN":
        return False
    if feature.information_policy == "PIT_SAFE":
        deps = parse_dependencies(feature.dependencies or [])
        if not any(d.dependency_type == "fundamental" for d in deps):
            return False
    return True
