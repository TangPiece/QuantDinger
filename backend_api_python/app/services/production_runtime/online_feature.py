"""Online Feature Runtime：复用 5F feature_parity 同源 evaluator。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.services.research_data.production_bridge.feature_parity import (
    OnlineFeatureEvaluator,
    default_score_evaluator,
)


@dataclass
class FeatureState:
    """在线特征状态（按 instrument × date）。"""

    feature_version: str = "online@1"
    processor_version: str = ""
    values: dict[tuple[str, str], float] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class OnlineFeatureEngine:
    """维护 FeatureState；求值函数与 5F OnlineFeatureEvaluator 同源。"""

    def __init__(
        self,
        *,
        feature_version: str = "online@1",
        processor_version: str = "",
        evaluate=None,
    ) -> None:
        self._feature_version = feature_version
        self._processor_version = processor_version
        self._evaluator = OnlineFeatureEvaluator(evaluate or default_score_evaluator)
        self._state = FeatureState(
            feature_version=feature_version,
            processor_version=processor_version,
        )

    @property
    def state(self) -> FeatureState:
        return self._state

    def compute(
        self,
        factor_rows: Sequence[Mapping[str, Any]],
        *,
        trading_date: str | None = None,
    ) -> FeatureState:
        """从 as-of factor rows 产出特征值，更新内部状态。"""
        rows = [dict(r) for r in factor_rows]
        if trading_date:
            # 仅保留当日或截至当日
            filtered = []
            for r in rows:
                td = str(r.get("trading_date") or r.get("datetime") or "")[:10]
                if not td or td <= trading_date:
                    filtered.append(r)
            rows = filtered
        values = self._evaluator.evaluate_rows(rows)
        # 物化带 score 的行供 Bridge infer
        out_rows: list[dict[str, Any]] = []
        for r in rows:
            td = str(r.get("trading_date") or "")[:10]
            inst = str(r.get("instrument_key") or r.get("instrument") or "")
            key = (td, inst)
            payload = dict(r)
            if key in values:
                payload["score"] = values[key]
            out_rows.append(payload)
        self._state = FeatureState(
            feature_version=self._feature_version,
            processor_version=self._processor_version,
            values=dict(values),
            rows=out_rows,
            metadata={"n_rows": len(out_rows), "n_values": len(values)},
        )
        return self._state
