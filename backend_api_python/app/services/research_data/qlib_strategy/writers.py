"""QlibRun → 本地/R2 Summary + Registry。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.research_data.contracts import QlibRunSummary
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import QlibRunArtifactStore
from .protocol import (
    ENGINE_VERSION,
    CompatibilityReport,
    QlibRunManifest,
    QlibStrategySpec,
)


class QlibRunWriter:
    """写 manifest / metrics / compatibility + Registry。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: QlibRunArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or QlibRunArtifactStore()

    def write(
        self,
        spec: QlibStrategySpec,
        *,
        qlib_run_hash: str,
        compatibility: CompatibilityReport,
        metrics: dict[str, Any],
        weights: pd.Series | None = None,
        predictions: pd.Series | None = None,
        nav_curve: list[dict[str, Any]] | None = None,
        backtest_hash: str = "",
        force: bool = False,
    ) -> QlibRunSummary:
        if not force:
            try:
                return self._registry.get_research_qlib_run(qlib_run_hash)
            except (KeyError, AttributeError):
                pass

        weight_records = _series_records(weights, value_key="weight")
        pred_records = _series_records(predictions, value_key="score")
        # metrics 内 nav_curve 不进 summary 体积；落盘单独文件
        metrics_clean = {
            k: v for k, v in dict(metrics or {}).items() if k != "nav_curve"
        }
        curve = nav_curve if nav_curve is not None else list(
            (metrics or {}).get("nav_curve") or []
        )
        summary = QlibRunSummary(
            qlib_run_hash=qlib_run_hash,
            strategy_hash=spec.strategy_hash,
            start_date=spec.start_date.isoformat(),
            end_date=spec.end_date.isoformat(),
            execution_policy=spec.execution_policy.mode,
            realism=spec.realism,
            market_rule=spec.market_rule if spec.realism == "NET" else "",
            dataset_ref=spec.dataset_ref or "",
            dataset_hash=spec.dataset_hash or "",
            materialization_id=spec.materialization_id or "",
            backtest_hash=str(backtest_hash or ""),
            compatibility_json=compatibility.model_dump(mode="json"),
            metrics_json=metrics_clean,
            engine_version=spec.qlib_engine_version or ENGINE_VERSION,
            metadata={
                "region": spec.region,
                "strategy_plan": "WEIGHT_FROM_TARGET_POSITION",
                "nav_points": len(curve),
            },
        )
        man = QlibRunManifest(
            qlib_run_hash=qlib_run_hash,
            strategy_hash=spec.strategy_hash,
            materialization_id=spec.materialization_id or "",
            engine_version=summary.engine_version,
        )
        art = self._artifacts.write_manifest(
            man,
            summary=summary,
            compatibility=compatibility,
            metrics=metrics_clean,
            prediction_records=pred_records,
            weight_records=weight_records,
            nav_curve=curve,
        )
        summary = summary.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_research_qlib_run(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary


def _series_records(
    series: pd.Series | None, *, value_key: str
) -> list[dict[str, Any]]:
    if series is None or series.empty:
        return []
    out: list[dict[str, Any]] = []
    for (dt, inst), v in series.items():
        out.append(
            {
                "datetime": str(pd.Timestamp(dt).date()),
                "instrument": str(inst),
                value_key: float(v),
            }
        )
    return out
