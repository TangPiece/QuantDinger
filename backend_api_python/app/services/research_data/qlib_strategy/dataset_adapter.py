"""Strategy → dataset_ref → Qlib cache（复用 1C Materializer / 2A ensure_cache）。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import StrategyResearchSummary
from app.services.research_data.qlib_adapter import QlibAdapter
from app.services.research_data.qlib_materializer.protocol import MaterializationResult

from .protocol import QlibStrategySpec


class DatasetAdaptError(RuntimeError):
    """数据集适配失败。"""


def resolve_dataset_ref(
    strategy: StrategyResearchSummary | None,
    spec: QlibStrategySpec,
    *,
    metadata: dict[str, Any] | None = None,
) -> str:
    """解析 dataset_ref：spec > metadata > strategy.factor_dataset_id。"""
    meta = dict(metadata or {})
    ref = (
        (spec.dataset_ref or "").strip()
        or str(meta.get("dataset_ref") or "").strip()
        or (strategy.factor_dataset_id if strategy else "")
        or str(meta.get("factor_dataset_id") or "").strip()
    )
    if not ref and not meta.get("skip_ensure_cache"):
        raise DatasetAdaptError("dataset_ref required for Qlib strategy run")
    return ref


def ensure_strategy_cache(
    adapter: QlibAdapter | None,
    dataset_ref: str,
    *,
    force: bool = False,
    metadata: dict[str, Any] | None = None,
) -> MaterializationResult | None:
    """调用 QlibAdapter.ensure_cache；测试可注入 materialization。"""
    meta = dict(metadata or {})
    if meta.get("skip_ensure_cache") or meta.get("materialization_id"):
        # 注入路径：构造最小 MaterializationResult 形态用 dict
        return None
    if adapter is None:
        raise DatasetAdaptError("QlibAdapter required when cache not injected")
    if not dataset_ref:
        raise DatasetAdaptError("empty dataset_ref")
    return adapter.ensure_cache(dataset_ref, force=force)
