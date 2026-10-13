"""A-share fundamental factors: fund_cn_basic@v1 (Canonical PIT + qd/factor + D1 meta).

Values never go into Level2 ``l2_factors`` hot table. Orchestration mirrors l2_daily
(markers, soft-fail D1 meta, local+R2 publish); data model follows Phase 1/4.
"""

from .catalog import (
    FACTOR_DEFINITIONS,
    FACTOR_SET,
    SUPPORT_METRICS,
    backtest_eligible_factors,
    coverage_matrix,
    factor_ids,
    mvp_factors,
    promote_factor_to_pit_safe,
    schema_hash,
)
from .expand import audit_status_table, pending_audit_factors, promote_many
from .orchestrator import run_pipeline, run_stage, run_coverage, run_pit_publish, run_compute_publish
from .register import register_mvp_factors, to_feature

__all__ = [
    "FACTOR_DEFINITIONS",
    "FACTOR_SET",
    "SUPPORT_METRICS",
    "audit_status_table",
    "backtest_eligible_factors",
    "coverage_matrix",
    "factor_ids",
    "mvp_factors",
    "pending_audit_factors",
    "promote_factor_to_pit_safe",
    "promote_many",
    "register_mvp_factors",
    "run_compute_publish",
    "run_coverage",
    "run_pipeline",
    "run_pit_publish",
    "run_stage",
    "schema_hash",
    "to_feature",
]
