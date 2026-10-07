"""MiningPolicy：生成 / 筛选 / 去重 / 复杂度上限。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from app.services.research_data.contracts import _ContractModel

from .protocol import GeneratorStrategy


class MiningPolicy(_ContractModel):
    """可版本化挖掘政策。"""

    policy_id: str
    version: str = "1.0.0"
    name: str = ""
    generator: GeneratorStrategy = "exhaustive_small"
    random_seed_required: bool = True
    max_candidates: int = 64
    max_depth: int = 2
    max_window: int = 252
    momentum_windows: list[int] = Field(default_factory=lambda: [5, 10, 20])
    volatility_windows: list[int] = Field(default_factory=lambda: [10, 20])
    rolling_windows: list[int] = Field(default_factory=lambda: [5, 10])
    rolling_fields: list[str] = Field(default_factory=lambda: ["close"])
    ref_windows: list[int] = Field(default_factory=lambda: [1, 5])
    ratio_pairs: list[tuple[str, str]] = Field(
        default_factory=lambda: [("close", "open"), ("high", "low")]
    )
    base_columns: list[str] = Field(default_factory=lambda: ["close", "open", "high", "low"])
    fast_screen_min_ic: float = 0.01
    dedup_by_expression_hash: bool = True
    corr_dedup_enabled: bool = False
    corr_dedup_top_n: int = 20
    corr_redundancy_threshold: float = 0.95
    max_full_evaluations: int = 32
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("max_candidates", "max_full_evaluations")
    @classmethod
    def _positive_cap(cls, v: int) -> int:
        if int(v) < 1:
            raise ValueError("cap must be >= 1")
        return int(v)

    @field_validator("max_window")
    @classmethod
    def _max_window(cls, v: int) -> int:
        v = int(v)
        if v < 1 or v > 252:
            raise ValueError("max_window must be in 1..252")
        return v

    @field_validator("momentum_windows", "volatility_windows", "rolling_windows", "ref_windows")
    @classmethod
    def _windows(cls, v: list[int]) -> list[int]:
        out = sorted({int(x) for x in v})
        if not out or any(x <= 0 for x in out):
            raise ValueError("windows must be positive")
        return out

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "generator": self.generator,
            "max_candidates": self.max_candidates,
            "max_depth": self.max_depth,
            "max_window": self.max_window,
            "momentum_windows": list(self.momentum_windows),
            "volatility_windows": list(self.volatility_windows),
            "rolling_windows": list(self.rolling_windows),
            "rolling_fields": list(self.rolling_fields),
            "ref_windows": list(self.ref_windows),
            "ratio_pairs": [list(p) for p in self.ratio_pairs],
            "base_columns": list(self.base_columns),
            "fast_screen_min_ic": float(self.fast_screen_min_ic),
            "dedup_by_expression_hash": self.dedup_by_expression_hash,
            "corr_dedup_enabled": self.corr_dedup_enabled,
            "corr_dedup_top_n": int(self.corr_dedup_top_n),
            "corr_redundancy_threshold": float(self.corr_redundancy_threshold),
            "max_full_evaluations": int(self.max_full_evaluations),
        }


__all__ = ["MiningPolicy"]
