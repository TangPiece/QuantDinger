"""FactorNeutralizationService：Raw Factor → Neutralized Factor Dataset。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.contracts import (
    FactorDatasetRecord,
    FactorNeutralizationSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import NeutralizationArtifactStore
from .exposure import ExposureProvider, InjectedExposureProvider
from .hash import compute_neutralization_hash
from .protocol import NeutralizationFrames, NeutralizationSpec
from .regression import RegressionNeutralizer
from .writers import NeutralizationDatasetWriter


class FactorNeutralizationError(RuntimeError):
    """中性化失败。"""


@dataclass
class NeutralizationResult:
    """中性化运行结果。"""

    neutralization_hash: str
    frames: NeutralizationFrames
    summary: FactorNeutralizationSummary
    neutralized_factor_dataset_id: str
    source: FactorDatasetRecord | None = None


class FactorNeutralizationService:
    """Factor Transformation；不复制 Evaluation Engine；不覆盖 Raw。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        exposure_provider: ExposureProvider | None = None,
        artifact_store: NeutralizationArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._default_provider = exposure_provider
        self._artifacts = artifact_store or NeutralizationArtifactStore()
        self._engine = RegressionNeutralizer()
        self._writer = NeutralizationDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def run(
        self,
        factor_dataset_id: str,
        spec: NeutralizationSpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> NeutralizationResult:
        """端到端：load factor → exposures → OLS → diagnostics → 双写。"""
        meta = dict(metadata or {})
        try:
            src = self._registry.get_factor_dataset(factor_dataset_id)
        except KeyError as exc:
            if meta.get("factor_records") is None:
                raise FactorNeutralizationError(
                    f"factor_dataset not found: {factor_dataset_id}"
                ) from exc
            src = None

        nspec = spec or NeutralizationSpec(factor_dataset_id=factor_dataset_id)
        if nspec.factor_dataset_id != factor_dataset_id:
            nspec = nspec.model_copy(update={"factor_dataset_id": factor_dataset_id})

        fhash = (
            (src.dataset_hash if src else "")
            or (src.factor_hash if src else "")
            or str(meta.get("factor_dataset_hash") or "injected")
        )
        nhash = compute_neutralization_hash(nspec, factor_dataset_hash=fhash)
        force = bool(meta.get("force_recompute"))

        if not force and meta.get("factor_records") is None and src is not None:
            try:
                summary = self._registry.get_factor_neutralization(nhash)
                return NeutralizationResult(
                    neutralization_hash=nhash,
                    frames=NeutralizationFrames(
                        neutralization_hash=nhash,
                        factor_dataset_id=factor_dataset_id,
                    ),
                    summary=summary,
                    neutralized_factor_dataset_id=summary.neutralized_factor_dataset_id,
                    source=src,
                )
            except KeyError:
                pass

        if "BETA" in nspec.targets and meta.get("exposure_rows") is None:
            # 无注入且无默认 provider 时硬失败
            if self._default_provider is None:
                raise FactorNeutralizationError(
                    "target BETA requested but Canonical BETA is unavailable; "
                    "inject metadata['exposure_rows'] or remove BETA from targets"
                )

        factor_rows = self._load_factor_rows(src, meta)
        provider = self._resolve_provider(meta)

        try:
            neu_rows, exp_rows, diags = self._engine.neutralize(
                factor_rows, provider, nspec
            )
        except Exception as exc:
            raise FactorNeutralizationError(str(exc)) from exc

        # 全日失败则报错
        ok = [r for r in neu_rows if r.neutralized_factor is not None]
        if not ok:
            raise FactorNeutralizationError(
                "neutralization produced no valid residuals "
                "(check min_cross_section_size / exposures / singular days)"
            )

        frames = NeutralizationFrames(
            neutralization_hash=nhash,
            factor_dataset_id=factor_dataset_id,
            factor_rows=neu_rows,
            exposure_rows=exp_rows,
            diagnostics=diags,
        )
        summary = self._writer.write(
            nspec,
            frames,
            factor_dataset_hash=fhash,
            raw_factor_ref=(src.factor_ref if src else str(meta.get("factor_ref") or "")),
            snapshot_id=(src.snapshot_id if src else str(meta.get("snapshot_id") or "")),
            universe_code=(
                src.universe_code if src else str(meta.get("universe_code") or "")
            ),
            force=force,
        )
        return NeutralizationResult(
            neutralization_hash=nhash,
            frames=frames,
            summary=summary,
            neutralized_factor_dataset_id=summary.neutralized_factor_dataset_id,
            source=src,
        )

    def _resolve_provider(self, meta: dict[str, Any]) -> ExposureProvider:
        if meta.get("exposure_rows") is not None:
            return InjectedExposureProvider(meta["exposure_rows"])
        if self._default_provider is not None:
            return self._default_provider
        raise FactorNeutralizationError(
            "no ExposureProvider: pass metadata['exposure_rows'] "
            "or construct service with exposure_provider="
        )

    def _load_factor_rows(
        self,
        src: FactorDatasetRecord | None,
        meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if meta.get("factor_records") is not None:
            return list(meta["factor_records"])
        if src is None:
            raise FactorNeutralizationError("no factor rows")
        from app.services.research_data import config as rd_config

        prefix = (
            f"{rd_config.canonical_prefix()}/factor/daily/factor_set={src.factor_ref}"
        )
        try:
            df = CanonicalRepository(self._store).read_parquet_df(prefix=prefix)
        except Exception as exc:
            raise FactorNeutralizationError(
                f"failed to load factor panel for {src.factor_dataset_id}"
            ) from exc
        if df is None or df.empty:
            raise FactorNeutralizationError("empty factor panel")
        return df.to_dict(orient="records")
