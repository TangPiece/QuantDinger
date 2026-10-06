"""Production Bridge Registry 协议。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import (
    ProductionBundleSummary,
    ProductionDeploymentRunSummary,
    ProductionDeploymentSummary,
)


class ProductionBridgeRepository(Protocol):
    def upsert_production_bundle(self, record: ProductionBundleSummary) -> None: ...

    def get_production_bundle(self, bundle_hash: str) -> ProductionBundleSummary: ...

    def upsert_production_deployment(
        self, record: ProductionDeploymentSummary
    ) -> None: ...

    def get_production_deployment(
        self, deployment_id: str
    ) -> ProductionDeploymentSummary: ...

    def get_active_deployment(
        self, strategy_code: str
    ) -> ProductionDeploymentSummary: ...

    def upsert_deployment_run(
        self, record: ProductionDeploymentRunSummary
    ) -> None: ...

    def get_deployment_run(self, run_id: str) -> ProductionDeploymentRunSummary: ...
