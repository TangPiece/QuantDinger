"""Dataset Feature → Qlib feature 映射（仅 OHLCV 基础列；禁语义漂移）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

# Domain 列名 → Qlib 字段名（不含 $ 前缀；表达式侧用 $close）
SUPPORTED_MARKET_FEATURES: dict[str, str] = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
    "vwap": "vwap",
}


class UnsupportedFeatureError(ValueError):
    """复杂/未知 Feature 拒绝映射，避免语义漂移。"""


def resolve_feature_name(feature: str) -> str:
    """将 Dataset.features 项解析为 Canonical market 列名。"""
    name = str(feature or "").strip()
    # 允许 $close / close / CLOSE
    if name.startswith("$"):
        name = name[1:]
    key = name.lower()
    if key not in SUPPORTED_MARKET_FEATURES:
        raise UnsupportedFeatureError(
            f"unsupported feature for Phase 1C materializer: {feature!r}; "
            f"allowed={sorted(SUPPORTED_MARKET_FEATURES)}"
        )
    return SUPPORTED_MARKET_FEATURES[key]


def build_feature_mapping(features: Sequence[str]) -> dict[str, dict[str, str]]:
    """生成 feature_mapping.json 内容。"""
    mapping: dict[str, dict[str, str]] = {}
    for feat in features:
        col = resolve_feature_name(feat)
        mapping[col] = {
            "source": f"canonical.market.{col}",
            "qlib_feature": f"${col}",
            "qlib_field": col,
        }
    return mapping


def write_feature_mapping_json(path: Path, mapping: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
