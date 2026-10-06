"""ProductionBridgeService：freeze → validate → promote → approve → deploy → infer。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import (
    CrossValidationSummary,
    ProductionBundleSummary,
    ProductionDeploymentSummary,
    StrategyResearchSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ProductionBundleArtifactStore
from .data_quality_gate import run_data_quality_gate
from .deployment import deploy_bundle, pause_bundle, rollback_deployment
from .feature_parity import run_feature_parity
from .freeze import FreezeError, build_bundle_spec, freeze_identity
from .inference import run_inference
from .integrity import assert_mutable, verify_bundle_integrity
from .protocol import (
    ENGINE_VERSION,
    InferenceRequest,
    InferenceResponse,
    ProductionBundleSpec,
)
from .state_machine import (
    StateTransitionError,
    assert_transition,
    cv_allows_candidate,
)
from .writers import ProductionBundleWriter


class ProductionBridgeError(RuntimeError):
    """Production Bridge 失败。"""


@dataclass
class BundleResult:
    bundle_hash: str
    summary: ProductionBundleSummary
    deployment: ProductionDeploymentSummary | None = None


class ProductionBridgeService:
    """Research → Production Bundle 编排。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: ProductionBundleArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or ProductionBundleArtifactStore()
        self._writer = ProductionBundleWriter(
            registry, artifact_store=self._artifacts
        )

    def freeze(
        self,
        strategy_hash: str,
        spec: ProductionBundleSpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> BundleResult:
        """组装并冻结 DRAFT Bundle。"""
        meta = dict(metadata or {})
        strategy = self._resolve_strategy(strategy_hash, meta)
        cv = self._resolve_cv(meta, strategy_hash=strategy_hash, spec=spec)
        if spec is None:
            spec = build_bundle_spec(strategy, cv, metadata=meta)
        elif not spec.cv_hash:
            spec = spec.model_copy(update={"cv_hash": cv.cv_hash})
        if spec.strategy_hash != strategy_hash:
            spec = spec.model_copy(update={"strategy_hash": strategy_hash})

        # 回填 CV 配对 hash
        updates = {}
        if not spec.backtest_hash and cv.backtest_hash:
            updates["backtest_hash"] = cv.backtest_hash
        if not spec.qlib_run_hash and cv.qlib_run_hash:
            updates["qlib_run_hash"] = cv.qlib_run_hash
        if updates:
            spec = spec.model_copy(update=updates)

        bhash, spec = freeze_identity(spec)
        force = bool(meta.get("force_recompute"))
        # parity（可选注入）
        parity = None
        if meta.get("factor_rows") is not None or meta.get("offline_rows") is not None:
            off = list(meta.get("offline_rows") or meta.get("factor_rows") or [])
            on = meta.get("online_rows")
            parity = run_feature_parity(off, on)

        summary = self._writer.write_bundle(
            spec, bundle_hash=bhash, status="DRAFT", parity=parity, force=force
        )
        return BundleResult(bundle_hash=bhash, summary=summary)

    def validate(
        self, bundle_hash: str, *, metadata: dict[str, Any] | None = None
    ) -> BundleResult:
        """DRAFT → VALIDATED：integrity + DQ + parity。"""
        meta = dict(metadata or {})
        summary = self._registry.get_production_bundle(bundle_hash)
        assert_mutable(summary)
        assert_transition(summary.status, "VALIDATED")

        g_int = verify_bundle_integrity(summary)
        if not g_int.passed:
            raise ProductionBridgeError(f"integrity failed: {g_int.message}")

        g_dq = run_data_quality_gate(
            summary,
            price_bars=meta.get("price_bars"),
            factor_rows=meta.get("factor_rows"),
            universe_membership=meta.get("universe_membership"),
        )
        if not g_dq.passed:
            raise ProductionBridgeError(f"data_quality failed: {g_dq.message}")

        if meta.get("factor_rows") is not None or meta.get("offline_rows") is not None:
            off = list(meta.get("offline_rows") or meta.get("factor_rows") or [])
            on = meta.get("online_rows")
            parity = run_feature_parity(off, on)
            if not parity.passed:
                raise ProductionBridgeError(
                    f"feature_parity failed: {parity.first_divergence}"
                )
            # 刷新 parity 报告文件
            from .protocol import BundleManifest

            self._artifacts.write_bundle(
                BundleManifest(
                    bundle_hash=bundle_hash,
                    strategy_hash=summary.strategy_hash,
                    engine_version=summary.engine_version or ENGINE_VERSION,
                ),
                summary=summary.model_copy(update={"status": "VALIDATED"}),
                dependency_lock=summary.dependency_lock_json,
                parity=parity,
            )

        updated = self._writer.update_status(bundle_hash, "VALIDATED")
        return BundleResult(bundle_hash=bundle_hash, summary=updated)

    def promote(
        self, bundle_hash: str, *, metadata: dict[str, Any] | None = None
    ) -> BundleResult:
        """VALIDATED → CANDIDATE（CV PASS 门禁）。"""
        meta = dict(metadata or {})
        summary = self._registry.get_production_bundle(bundle_hash)
        assert_mutable(summary)
        assert_transition(summary.status, "CANDIDATE")

        cv_status = str(meta.get("cv_status") or "")
        if not cv_status:
            try:
                cv = self._registry.get_research_cross_validation(summary.cv_hash)
                cv_status = cv.status
            except KeyError:
                if meta.get("allow_missing_cv"):
                    cv_status = "PASSED"
                else:
                    raise ProductionBridgeError(
                        f"cv_hash not found: {summary.cv_hash}"
                    ) from None
        if not cv_allows_candidate(cv_status):
            raise ProductionBridgeError(
                f"cv status {cv_status!r} cannot promote to CANDIDATE"
            )
        updated = self._writer.update_status(
            bundle_hash, "CANDIDATE", metadata={"cv_status": cv_status}
        )
        return BundleResult(bundle_hash=bundle_hash, summary=updated)

    def approve(self, bundle_hash: str) -> BundleResult:
        """CANDIDATE → APPROVED（此后不可变）。"""
        summary = self._registry.get_production_bundle(bundle_hash)
        assert_mutable(summary)
        assert_transition(summary.status, "APPROVED")
        updated = self._writer.update_status(bundle_hash, "APPROVED")
        return BundleResult(bundle_hash=bundle_hash, summary=updated)

    def deploy(self, bundle_hash: str) -> BundleResult:
        """APPROVED/PAUSED → DEPLOYED。"""
        summary = self._registry.get_production_bundle(bundle_hash)
        updated, dep = deploy_bundle(self._registry, self._writer, summary)
        return BundleResult(
            bundle_hash=bundle_hash, summary=updated, deployment=dep
        )

    def pause(self, bundle_hash: str) -> BundleResult:
        summary = self._registry.get_production_bundle(bundle_hash)
        updated = pause_bundle(self._writer, summary)
        return BundleResult(bundle_hash=bundle_hash, summary=updated)

    def rollback(
        self, strategy_code: str, to_bundle_hash: str
    ) -> BundleResult:
        updated, dep = rollback_deployment(
            self._registry,
            self._writer,
            strategy_code=strategy_code,
            to_bundle_hash=to_bundle_hash,
        )
        return BundleResult(
            bundle_hash=updated.bundle_hash, summary=updated, deployment=dep
        )

    def infer(
        self,
        request: InferenceRequest,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> InferenceResponse:
        """干跑推理 → OrderIntent。"""
        meta = dict(metadata or {})
        summary = self._registry.get_production_bundle(request.bundle_hash)
        resp = run_inference(
            summary,
            request,
            factor_rows=meta.get("factor_rows") or meta.get("signal_rows"),
            price_bars=meta.get("price_bars"),
            universe_membership=meta.get("universe_membership"),
            current_positions=meta.get("current_positions"),
            notional=float(meta.get("notional") or 1_000_000.0),
            max_single_weight=float(meta.get("max_single_weight") or 1.0),
            max_gross_exposure=float(meta.get("max_gross_exposure") or 1.0),
        )
        dep_id = ""
        try:
            code = summary.strategy_code or summary.strategy_hash[:16]
            dep_id = self._registry.get_active_deployment(code).deployment_id
        except Exception:
            pass
        self._writer.write_run(resp, deployment_id=dep_id)
        return resp

    def _resolve_strategy(
        self, strategy_hash: str, meta: dict[str, Any]
    ) -> StrategyResearchSummary | None:
        try:
            return self._registry.get_strategy_research(strategy_hash)
        except KeyError:
            if meta.get("signal_definition_json") is not None or meta.get(
                "allow_missing_strategy"
            ):
                return None
            raise ProductionBridgeError(
                f"strategy_research not found: {strategy_hash}"
            ) from None

    def _resolve_cv(
        self,
        meta: dict[str, Any],
        *,
        strategy_hash: str,
        spec: ProductionBundleSpec | None,
    ) -> CrossValidationSummary:
        cv_hash = (spec.cv_hash if spec else "") or str(meta.get("cv_hash") or "")
        if cv_hash:
            try:
                return self._registry.get_research_cross_validation(cv_hash)
            except KeyError:
                if not meta.get("inject_cv"):
                    raise ProductionBridgeError(
                        f"cv not found: {cv_hash}"
                    ) from None
        if meta.get("inject_cv"):
            raw = dict(meta["inject_cv"])
            raw.setdefault("strategy_hash", strategy_hash)
            raw.setdefault("cv_hash", cv_hash or f"cv_inject_{strategy_hash[:12]}")
            raw.setdefault("status", "PASSED")
            return CrossValidationSummary.model_validate(raw)
        raise ProductionBridgeError("cv_hash required for freeze")


# re-export errors for tests
__all__ = [
    "BundleResult",
    "FreezeError",
    "ProductionBridgeError",
    "ProductionBridgeService",
    "StateTransitionError",
]
