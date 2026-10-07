"""Phase 8A：StrategyRegistryService 门面（无 promote LIVE / Validation Gate）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .bindings import merge_bindings, normalize_policy_bindings
from .bridge_from_production import version_record_from_production_bundle
from .bridge_to_governance import link_governance_active
from .identity import InvalidStrategyIdentityError, normalize_strategy_code
from .pin import content_hash_for_version_record
from .protocol import StrategyRecord, StrategyVersionRecord, VersionSource
from .resolver import resolve_version
from .writers import StrategyRegistryWriter


class RegistryError(RuntimeError):
    pass


class VersionImmutableError(RuntimeError):
    """已注册版本禁止修改钉扎字段或 policy。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_pin_compatible(existing: StrategyVersionRecord, candidate: StrategyVersionRecord) -> None:
    """同 (code, version) 重复注册：content 一致则幂等，否则拒。"""
    lock_fields = (
        "dataset_hash",
        "snapshot_id",
        "model_version",
        "model_artifact_id",
        "feature_version",
        "processor_version",
        "processor_hash",
        "strategy_hash",
        "bundle_hash",
        "risk_policy_ref",
        "execution_policy_ref",
        "content_hash",
    )
    for key in lock_fields:
        if getattr(existing, key) != getattr(candidate, key):
            raise VersionImmutableError(f"{key} is immutable after register")


class StrategyRegistryService:
    """Research → Production 策略身份 SSOT；不提交 OMS、不自动 LIVE。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        production_bridge: Any | None = None,
        governance: Any | None = None,
        writer: StrategyRegistryWriter | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._production_bridge = production_bridge
        self._governance = governance
        self._writer = writer or StrategyRegistryWriter(registry)
        self._strategies: dict[str, StrategyRecord] = {}
        self._versions: dict[str, StrategyVersionRecord] = {}
        self._by_code_version: dict[tuple[str, str], str] = {}

    def _load_version_indexes(self) -> None:
        """从 registry 回填进程内索引（测试/verify 用）。"""
        for rec in self._registry.list_strategy_version_bindings():
            ver = self._binding_to_record(rec)
            self._versions[ver.version_id] = ver
            self._by_code_version[(ver.strategy_code, ver.strategy_version)] = ver.version_id
        try:
            for row in self._registry.list_strategy_registry():
                self._strategies[row.strategy_code] = StrategyRecord(
                    strategy_code=row.strategy_code,
                    display_name=row.display_name,
                    owner=row.owner,
                    status=row.status,  # type: ignore[arg-type]
                    active_version=row.active_version,
                    created_at=row.created_at or "",
                    metadata=dict(row.metadata or {}),
                )
        except Exception:
            pass

    @staticmethod
    def _binding_to_record(binding: Any) -> StrategyVersionRecord:
        return StrategyVersionRecord(
            version_id=binding.version_id,
            strategy_code=binding.strategy_code,
            strategy_version=binding.strategy_version,
            dataset_hash=binding.dataset_hash,
            snapshot_id=binding.snapshot_id,
            model_version=binding.model_version,
            model_artifact_id=binding.model_artifact_id,
            feature_version=binding.feature_version,
            processor_version=binding.processor_version,
            processor_hash=binding.processor_hash,
            strategy_hash=binding.strategy_hash,
            bundle_hash=binding.bundle_hash,
            risk_policy_ref=binding.risk_policy_ref,
            execution_policy_ref=binding.execution_policy_ref,
            content_hash=binding.content_hash,
            registered_at=binding.registered_at,
            source=binding.source,  # type: ignore[arg-type]
            storage_uri=binding.storage_uri,
            immutable=True,
            metadata=dict(binding.metadata or {}),
        )

    def register_strategy(
        self,
        strategy_code: str,
        *,
        display_name: str = "",
        owner: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> StrategyRecord:
        code = normalize_strategy_code(strategy_code)
        existing = self._strategies.get(code)
        if existing is not None:
            return existing
        rec = StrategyRecord(
            strategy_code=code,
            display_name=display_name or code,
            owner=owner,
            created_at=_now(),
            metadata=dict(metadata or {}),
        )
        self._strategies[code] = rec
        self._writer.write_strategy(rec)
        return rec

    def register_version_from_bundle(
        self,
        bundle_hash: str,
        *,
        strategy_version_label: str,
        risk_policy_ref: str = "",
        execution_policy_ref: str | None = None,
    ) -> StrategyVersionRecord:
        bundle = self._registry.get_production_bundle(str(bundle_hash).strip())
        draft = version_record_from_production_bundle(
            bundle,
            strategy_version_label=strategy_version_label,
            risk_policy_ref=risk_policy_ref,
            execution_policy_ref=execution_policy_ref,
            source="BUNDLE",
        )
        return self._persist_version(draft)

    def register_version_manual(
        self,
        strategy_code: str,
        strategy_version: str,
        *,
        dataset_hash: str = "",
        snapshot_id: str = "",
        model_version: str = "",
        model_artifact_id: str = "",
        feature_version: str = "",
        processor_version: str = "",
        processor_hash: str = "",
        strategy_hash: str = "",
        bundle_hash: str = "",
        risk_policy_ref: str = "",
        execution_policy_ref: str = "NEXT_OPEN",
        source: VersionSource = "MANUAL",
        metadata: Mapping[str, Any] | None = None,
    ) -> StrategyVersionRecord:
        code = normalize_strategy_code(strategy_code)
        self.register_strategy(code)
        label = str(strategy_version).strip()
        if not label:
            raise RegistryError("strategy_version required")
        bindings = normalize_policy_bindings(
            risk_policy_ref=risk_policy_ref,
            execution_policy_ref=execution_policy_ref,
        )
        content_hash = content_hash_for_version_record(
            strategy_version=label,
            model_version=model_version,
            dataset_hash=dataset_hash,
            feature_version=feature_version,
            strategy_hash=strategy_hash,
            bundle_hash=bundle_hash,
            snapshot_id=snapshot_id,
            model_artifact_id=model_artifact_id,
            processor_version=processor_version,
            processor_hash=processor_hash,
            risk_policy_ref=bindings.risk_policy_ref,
            execution_policy_ref=bindings.execution_policy_ref,
        )
        version_id = f"{code}@{label}@{content_hash[:8]}"
        draft = StrategyVersionRecord(
            version_id=version_id,
            strategy_code=code,
            strategy_version=label,
            dataset_hash=dataset_hash,
            snapshot_id=snapshot_id,
            model_version=model_version,
            model_artifact_id=model_artifact_id,
            feature_version=feature_version,
            processor_version=processor_version,
            processor_hash=processor_hash,
            strategy_hash=strategy_hash,
            bundle_hash=bundle_hash,
            risk_policy_ref=bindings.risk_policy_ref,
            execution_policy_ref=bindings.execution_policy_ref,
            content_hash=content_hash,
            registered_at=_now(),
            source=source,
            immutable=True,
            metadata=dict(metadata or {}),
        )
        return self._persist_version(draft)

    def _persist_version(self, draft: StrategyVersionRecord) -> StrategyVersionRecord:
        key = (draft.strategy_code, draft.strategy_version)
        existing_id = self._by_code_version.get(key)
        if existing_id:
            existing = self._versions[existing_id]
            if existing.content_hash == draft.content_hash:
                return existing
            _assert_pin_compatible(existing, draft)
            return existing
        self.register_strategy(draft.strategy_code)
        saved = self._writer.write_version(draft)
        self._versions[saved.version_id] = saved
        self._by_code_version[key] = saved.version_id
        return saved

    def set_policy_bindings(
        self,
        strategy_code: str,
        version: str,
        *,
        risk_ref: str | None = None,
        execution_ref: str | None = None,
    ) -> StrategyVersionRecord:
        """仅允许在版本尚未注册时调整 policy；已注册须新版本。"""
        code = normalize_strategy_code(strategy_code)
        label = str(version).strip()
        vid = self._by_code_version.get((code, label))
        if vid is None:
            raise RegistryError("version not found; register first")
        existing = self._versions[vid]
        if existing.immutable and existing.registered_at:
            raise VersionImmutableError("policy bindings immutable; register new version")
        bindings = merge_bindings(
            normalize_policy_bindings(
                risk_policy_ref=existing.risk_policy_ref,
                execution_policy_ref=existing.execution_policy_ref,
            ),
            risk_policy_ref=risk_ref,
            execution_policy_ref=execution_ref,
        )
        patched = existing.model_copy(
            update={
                "risk_policy_ref": bindings.risk_policy_ref,
                "execution_policy_ref": bindings.execution_policy_ref,
                "content_hash": content_hash_for_version_record(
                    strategy_version=existing.strategy_version,
                    model_version=existing.model_version,
                    dataset_hash=existing.dataset_hash,
                    feature_version=existing.feature_version,
                    strategy_hash=existing.strategy_hash,
                    bundle_hash=existing.bundle_hash,
                    snapshot_id=existing.snapshot_id,
                    model_artifact_id=existing.model_artifact_id,
                    processor_version=existing.processor_version,
                    processor_hash=existing.processor_hash,
                    risk_policy_ref=bindings.risk_policy_ref,
                    execution_policy_ref=bindings.execution_policy_ref,
                ),
            }
        )
        # 8A：注册后 immutable，此分支理论上不可达
        return self._persist_version(patched)

    def get_version(
        self, strategy_code: str, version: str
    ) -> StrategyVersionRecord:
        code = normalize_strategy_code(strategy_code)
        vid = self._by_code_version.get((code, str(version).strip()))
        if vid is None:
            raise RegistryError("version not found")
        return self._versions[vid]

    def get_active(self, strategy_code: str) -> StrategyVersionRecord | None:
        code = normalize_strategy_code(strategy_code)
        strat = self._strategies.get(code)
        if strat is None or not strat.active_version:
            try:
                row = self._registry.get_strategy_registry(code)
                if not row.active_version:
                    return None
                return self.get_version(code, row.active_version)
            except Exception:
                return None
        return self.get_version(code, strat.active_version)

    def list_versions(self, strategy_code: str) -> list[StrategyVersionRecord]:
        code = normalize_strategy_code(strategy_code)
        out = [v for v in self._versions.values() if v.strategy_code == code]
        out.sort(key=lambda v: v.registered_at)
        return out

    def resolve(
        self,
        *,
        code: str | None = None,
        strategy_hash: str | None = None,
        bundle_hash: str | None = None,
        version: str | None = None,
    ) -> StrategyVersionRecord:
        strat = self._strategies.get(normalize_strategy_code(code)) if code else None
        active = strat.active_version if strat else None
        return resolve_version(
            self._versions.values(),
            strategy_code=code,
            strategy_hash=strategy_hash,
            bundle_hash=bundle_hash,
            version=version,
            active_version=active if version is None and not strategy_hash and not bundle_hash else None,
        )

    def link_governance_active(
        self, strategy_code: str, version: str
    ) -> StrategyVersionRecord:
        """写 7E active_version；不 promote LIVE。"""
        ver = self.get_version(strategy_code, version)
        link_governance_active(self._registry, ver, self._governance)
        code = ver.strategy_code
        strat = self._strategies.get(code) or StrategyRecord(
            strategy_code=code, created_at=_now()
        )
        strat = strat.model_copy(update={"active_version": ver.strategy_version})
        self._strategies[code] = strat
        self._writer.write_strategy(strat)
        return ver


__all__ = [
    "InvalidStrategyIdentityError",
    "RegistryError",
    "StrategyRegistryService",
    "VersionImmutableError",
]
