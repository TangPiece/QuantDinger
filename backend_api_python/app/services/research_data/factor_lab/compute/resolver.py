"""Dependency DAG：拓扑序 + 环检测（复用 4A 解析）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.factor_lab.dependencies import (
    FactorDependencyError,
    parse_dependency,
    validate_dependencies,
)
from app.services.research_data.registry import ResearchRegistry


@dataclass
class DependencyDAG:
    """因子依赖 DAG。"""

    root_ref: str
    # 拓扑序：数据依赖节点 + factor refs（根在最后）
    order: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


def resolve_dependency_dag(
    feature: FeatureDefinition,
    registry: ResearchRegistry,
) -> DependencyDAG:
    """解析并校验依赖，输出稳定拓扑序。

    - factor 依赖必须为 ``code@version``
    - 检测环 / 缺失
    """
    validate_dependencies(feature, registry, check_cycles=True)
    root = f"{feature.code}@{feature.version}"
    edges: list[tuple[str, str]] = []
    data_nodes: set[str] = set()
    factor_nodes: set[str] = {root}

    def visit_factor(ref: str) -> None:
        feat = registry.get_feature(ref)
        for raw in feat.dependencies or []:
            dep = parse_dependency(raw)
            if dep.dependency_type == "factor":
                if "@" not in dep.dependency_code:
                    raise FactorDependencyError(
                        f"factor dependency must include version: {dep.dependency_code!r}"
                    )
                child = dep.dependency_code
                factor_nodes.add(child)
                edges.append((ref, child))
                visit_factor(child)
            else:
                node = f"{dep.dependency_type}:{dep.dependency_code}"
                data_nodes.add(node)
                edges.append((ref, node))

    visit_factor(root)

    # Kahn 拓扑：仅 factor 子图（数据节点无入边依赖）
    indeg: dict[str, int] = {n: 0 for n in factor_nodes}
    children: dict[str, list[str]] = {n: [] for n in factor_nodes}
    for src, dst in edges:
        if dst in factor_nodes and src in factor_nodes:
            # edge src → dst means src depends on dst → reverse for topo (dst before src)
            children.setdefault(dst, []).append(src)
            indeg[src] = indeg.get(src, 0) + 1
            indeg.setdefault(dst, indeg.get(dst, 0))

    queue = sorted([n for n, d in indeg.items() if d == 0])
    topo: list[str] = []
    while queue:
        n = queue.pop(0)
        topo.append(n)
        for m in sorted(children.get(n, [])):
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
                queue.sort()
    if len(topo) != len(factor_nodes):
        raise FactorDependencyError("dependency cycle detected in DAG")

    # 稳定顺序：数据节点字典序 + factor 拓扑
    order = sorted(data_nodes) + topo
    return DependencyDAG(root_ref=root, order=order, edges=edges)
