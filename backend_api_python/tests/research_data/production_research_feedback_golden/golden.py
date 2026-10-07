"""Phase 8H Golden：Fake inject + Production Research Feedback 脚手架。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.production_research_feedback.runner import ProductionResearchFeedbackService
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.data_query import DataQuery
from app.services.research_data.registry import LocalJsonRegistry

from strategy_monitoring_golden.golden import STRATEGY_CODE


def golden_production_feedback_inject() -> dict[str, Any]:
    return {
        "production_feedback": {
            "as_of_time": "2025-06-01T12:00:00+00:00",
            "pnl_total": 1000.0,
            "metrics": {"return_total": 0.03, "sharpe": 0.8},
            "lineage": {
                "comparison_run_id": "pcmp_golden_1",
                "incident_id": "gr_inc_golden",
                "dataset_hash": "ds_hash_golden",
                "strategy_version": "v_live",
            },
            "rows": [
                {
                    "metric": "return_total",
                    "value": 0.03,
                    "as_of_time": "2025-06-01T12:00:00+00:00",
                    "source_artifact_id": "pcmp_golden_1",
                    "source_phase": "8E",
                },
                {
                    "metric": "pnl_component",
                    "value": 1000.0,
                    "as_of_time": "2025-06-01T12:00:00+00:00",
                    "source_artifact_id": "pcmp_golden_1",
                    "source_phase": "8E",
                },
            ],
        }
    }


def golden_bad_pit_lineage_inject() -> dict[str, Any]:
    return {
        "production_feedback": {
            "rows": [{"metric": "x", "value": 1.0, "as_of_time": ""}],
            "lineage": {},
        }
    }


def make_feedback_env(
    tmp: Path,
) -> tuple[ProductionResearchFeedbackService, LocalJsonRegistry, DataQuery]:
    reg = LocalJsonRegistry(root=tmp / "registry")
    store = LocalCanonicalStore(root=tmp / "canonical")
    dq = DataQuery(store, reg)
    svc = ProductionResearchFeedbackService(
        store,
        reg,
        data_query=dq,
    )
    svc._writer._artifacts.root = tmp / "artifacts"
    return svc, reg, dq


__all__ = [
    "STRATEGY_CODE",
    "golden_bad_pit_lineage_inject",
    "golden_production_feedback_inject",
    "make_feedback_env",
]
