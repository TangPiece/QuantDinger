"""Phase 4D：IC / RankIC / ICIR Metrics。"""

from .aggregator import ICStatisticsAggregator
from .artifact_store import MetricArtifactStore, validate_metric_manifest
from .calculators import (
    CrossSectionalICEngine,
    PearsonICCalculator,
    SpearmanRankICCalculator,
)
from .hash import compute_metric_hash
from .orchestrator import FactorMetricsError, FactorMetricsService, MetricsResult
from .protocol import (
    CALCULATOR_VERSION,
    METRIC_VERSION,
    FactorEvaluationSummary,
    MetricPoint,
    MetricSpec,
    MetricTimeSeries,
)

__all__ = [
    "CALCULATOR_VERSION",
    "METRIC_VERSION",
    "CrossSectionalICEngine",
    "FactorEvaluationSummary",
    "FactorMetricsError",
    "FactorMetricsService",
    "ICStatisticsAggregator",
    "MetricArtifactStore",
    "MetricPoint",
    "MetricSpec",
    "MetricTimeSeries",
    "MetricsResult",
    "PearsonICCalculator",
    "SpearmanRankICCalculator",
    "compute_metric_hash",
    "validate_metric_manifest",
]
