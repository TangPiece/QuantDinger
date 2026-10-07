"""Phase 9G / 10E: Experiment registry (read + minimal register)."""

from .service import ExperimentPlatformError, ExperimentPlatformService, get_experiment_platform_service

__all__ = [
    "ExperimentPlatformError",
    "ExperimentPlatformService",
    "get_experiment_platform_service",
]
