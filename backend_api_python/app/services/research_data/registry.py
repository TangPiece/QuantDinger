"""研究 Registry：D1 qd_research，未配置时用本地 JSON 供单测。"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from . import config, d1_client
from .contracts import (
    ArtifactRecord,
    ConsistencyRunRecord,
    DataVersionRef,
    DatasetDefinition,
    DatasetHandle,
    EvaluationDatasetRecord,
    ExperimentDefinition,
    FactorDatasetRecord,
    FactorEvaluationSummary,
    FactorNeutralizationSummary,
    FactorStabilitySummary,
    FeatureDefinition,
    GroupEvaluationSummary,
    ModelDefinition,
    ModelVersionRecord,
    PricePolicy,
    ProcessorDefinition,
    SignalRunRecord,
    SnapshotRef,
)
from .hashing import canonical_json, compute_dataset_hash


class ProcessorImmutabilityError(ValueError):
    """同一 code@version 禁止修改 pipeline；须 bump version。"""


class FeatureImmutabilityError(ValueError):
    """同一 feature code@version 禁止修改定义；须 bump version。"""


class ModelImmutabilityError(ValueError):
    """同一 model code@version 禁止修改 config；须 bump version。"""


def _assert_model_version_immutable(
    existing_raw: dict[str, Any],
    record: ModelVersionRecord,
) -> None:
    """已存在的 model_version 若 config 变化则拒绝。"""
    old_cfg = existing_raw.get("config") if isinstance(existing_raw, dict) else None
    new_cfg = record.model_dump(mode="json").get("config")
    if canonical_json(old_cfg or {}) != canonical_json(new_cfg or {}):
        raise ModelImmutabilityError(
            f"model version {record.model_code}@{record.version} is immutable; "
            "bump version to change config"
        )


def _assert_processor_immutable(
    existing_raw: dict[str, Any],
    processor: ProcessorDefinition,
) -> None:
    """已存在的 processor 若 pipeline 内容变化则拒绝。"""
    old_pipe = existing_raw.get("pipeline") if isinstance(existing_raw, dict) else None
    new_pipe = processor.model_dump(mode="json").get("pipeline")
    if canonical_json(old_pipe or []) != canonical_json(new_pipe or []):
        raise ProcessorImmutabilityError(
            f"processor {processor.code}@{processor.version} is immutable; "
            "bump version to change pipeline"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ResearchRegistry(Protocol):
    def upsert_data_version(
        self,
        *,
        dataset_code: str,
        version: str,
        schema_version: str,
        status: str,
        checksum: str,
        r2_uri: str,
        row_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int: ...

    def create_snapshot(
        self,
        *,
        snapshot_id: str,
        name: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str: ...

    def upsert_dataset(
        self, definition: DatasetDefinition, *, status: str = "ACTIVE"
    ) -> None: ...

    def get_dataset(self, dataset_ref: str) -> DatasetHandle: ...

    def upsert_feature(self, feature: FeatureDefinition) -> None: ...

    def get_feature(self, feature_ref: str) -> FeatureDefinition: ...

    def upsert_processor(self, processor: ProcessorDefinition) -> None: ...

    def get_processor(self, processor_ref: str) -> ProcessorDefinition: ...

    def upsert_universe_ref(
        self,
        *,
        universe_code: str,
        pg_universe_id: int | None,
        market: str | None,
    ) -> None: ...

    def get_snapshot(self, snapshot_id: str) -> SnapshotRef: ...

    def upsert_model(self, model: ModelDefinition) -> None: ...

    def get_model(self, model_code: str) -> ModelDefinition: ...

    def upsert_model_version(self, record: ModelVersionRecord) -> None: ...

    def get_model_version(self, model_version_ref: str) -> ModelVersionRecord: ...

    def upsert_artifact(self, record: ArtifactRecord) -> None: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord: ...

    def upsert_experiment(self, experiment: ExperimentDefinition) -> None: ...

    def get_experiment(self, experiment_id: str) -> ExperimentDefinition: ...

    def upsert_signal_run(self, record: SignalRunRecord) -> None: ...

    def get_signal_run(self, signal_run_id: str) -> SignalRunRecord: ...

    def upsert_consistency_run(self, record: ConsistencyRunRecord) -> None: ...

    def get_consistency_run(self, run_id: str) -> ConsistencyRunRecord: ...

    def upsert_factor_dataset(self, record: FactorDatasetRecord) -> None: ...

    def get_factor_dataset(self, factor_dataset_id: str) -> FactorDatasetRecord: ...

    def upsert_evaluation_dataset(self, record: EvaluationDatasetRecord) -> None: ...

    def get_evaluation_dataset(self, evaluation_hash: str) -> EvaluationDatasetRecord: ...

    def upsert_factor_evaluation_summary(
        self, record: FactorEvaluationSummary
    ) -> None: ...

    def get_factor_evaluation_summary(
        self, metric_hash: str, horizon: int
    ) -> FactorEvaluationSummary: ...

    def upsert_factor_group_evaluation(
        self, record: GroupEvaluationSummary
    ) -> None: ...

    def get_factor_group_evaluation(
        self, group_evaluation_hash: str, horizon: int
    ) -> GroupEvaluationSummary: ...

    def upsert_factor_stability_evaluation(
        self, record: FactorStabilitySummary
    ) -> None: ...

    def get_factor_stability_evaluation(
        self, stability_hash: str, horizon: int
    ) -> FactorStabilitySummary: ...

    def upsert_factor_neutralization(
        self, record: FactorNeutralizationSummary
    ) -> None: ...

    def get_factor_neutralization(
        self, neutralization_hash: str
    ) -> FactorNeutralizationSummary: ...


class LocalJsonRegistry:
    """本地 JSON Registry，测试默认后端。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or config.research_cache_dir() / "registry")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._path = self.root / "registry.json"
        if not self._path.is_file():
            self._write(
                {
                    "data_versions": {},
                    "snapshots": {},
                    "datasets": {},
                    "features": {},
                    "processors": {},
                    "models": {},
                    "model_versions": {},
                    "artifacts": {},
                    "experiments": {},
                    "signal_runs": {},
                    "consistency_runs": {},
                    "factor_datasets": {},
                    "evaluation_datasets": {},
                    "factor_evaluation_summaries": {},
                    "factor_group_evaluations": {},
                    "factor_stability_evaluations": {},
                    "factor_neutralizations": {},
                    "universe_refs": {},
                    "_seq": 0,
                }
            )

    def _read(self) -> dict[str, Any]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert_data_version(
        self,
        *,
        dataset_code: str,
        version: str,
        schema_version: str,
        status: str,
        checksum: str,
        r2_uri: str,
        row_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self._lock:
            data = self._read()
            key = f"{dataset_code}@{version}"
            seq = int(data.get("_seq") or 0) + 1
            data["_seq"] = seq
            data["data_versions"][key] = {
                "data_version_id": seq,
                "dataset_code": dataset_code,
                "version": version,
                "schema_version": schema_version,
                "status": status,
                "checksum": checksum,
                "r2_uri": r2_uri,
                "row_count": row_count,
                "metadata": metadata or {},
                "created_at": _utc_now(),
            }
            self._write(data)
            return seq

    def create_snapshot(
        self,
        *,
        snapshot_id: str,
        name: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        with self._lock:
            data = self._read()
            data["snapshots"][snapshot_id] = {
                "snapshot_id": snapshot_id,
                "name": name,
                "created_at": _utc_now(),
                "metadata": metadata or {},
                "items": items,
            }
            self._write(data)
            return snapshot_id

    def upsert_dataset(
        self, definition: DatasetDefinition, *, status: str = "ACTIVE"
    ) -> None:
        """登记 Dataset；status 存旁路字段（Local JSON），供 validated 等验收态。"""
        with self._lock:
            data = self._read()
            key = f"{definition.code}@{definition.version}"
            payload = definition.model_dump(mode="json")
            # Domain Contract 无 status 字段；Registry 侧单独记录
            payload["_registry_status"] = status
            data["datasets"][key] = payload
            self._write(data)

    def get_dataset(self, dataset_ref: str) -> DatasetHandle:
        code, version = _split_ref(dataset_ref)
        data = self._read()
        raw = data["datasets"].get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"dataset not found: {dataset_ref}")
        # 剥离 Registry 旁路字段，避免 DatasetDefinition extra=forbid 失败
        payload = {k: v for k, v in raw.items() if not str(k).startswith("_")}
        definition = DatasetDefinition.model_validate(payload)
        snapshot = self.get_snapshot(definition.snapshot_id)
        digest = compute_dataset_hash(
            dataset_definition=definition.model_dump(mode="json"),
            dataset_version=definition.version,
            snapshot_id=definition.snapshot_id,
            schema_version=definition.schema_version,
            processor_version=definition.processor or "",
            materializer_version="none",
            price_policy=definition.price_policy.model_dump(mode="json"),
        )
        return DatasetHandle(
            definition=definition,
            snapshot=snapshot,
            dataset_hash=digest,
            manifest_uri="",
        )

    def upsert_feature(self, feature: FeatureDefinition) -> None:
        """登记 Feature/Factor；同 code@version 且 factor_hash 变化则拒绝。"""
        from app.services.research_data.factor_lab.hash import compute_factor_hash
        from app.services.research_data.factor_lab.immutability import (
            FeatureImmutabilityError as _FIE,
            assert_feature_immutable,
            ensure_factor_hash,
        )

        feat = ensure_factor_hash(feature)
        feat = feat.model_copy(update={"factor_hash": compute_factor_hash(feat)})
        with self._lock:
            data = self._read()
            data.setdefault("features", {})
            key = f"{feat.code}@{feat.version}"
            existing = data["features"].get(key)
            if existing is not None:
                try:
                    assert_feature_immutable(existing, feat)
                except _FIE as exc:
                    raise FeatureImmutabilityError(str(exc)) from exc
                return
            data["features"][key] = feat.model_dump(mode="json")
            self._write(data)

    def get_feature(self, feature_ref: str) -> FeatureDefinition:
        code, version = _split_ref(feature_ref)
        data = self._read()
        raw = data["features"].get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"feature not found: {feature_ref}")
        return FeatureDefinition.model_validate(raw)

    def upsert_processor(self, processor: ProcessorDefinition) -> None:
        """登记 ProcessorDefinition；同 code@version 禁止改 pipeline。"""
        with self._lock:
            data = self._read()
            data.setdefault("processors", {})
            key = f"{processor.code}@{processor.version}"
            existing = data["processors"].get(key)
            if existing is not None:
                _assert_processor_immutable(existing, processor)
                return  # 幂等：内容相同则跳过
            data["processors"][key] = processor.model_dump(mode="json")
            self._write(data)

    def get_processor(self, processor_ref: str) -> ProcessorDefinition:
        """读取 `code@version` Processor。"""
        code, version = _split_ref(processor_ref)
        data = self._read()
        raw = (data.get("processors") or {}).get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"processor not found: {processor_ref}")
        return ProcessorDefinition.model_validate(raw)

    def upsert_universe_ref(
        self,
        *,
        universe_code: str,
        pg_universe_id: int | None,
        market: str | None,
    ) -> None:
        with self._lock:
            data = self._read()
            data["universe_refs"][universe_code] = {
                "universe_code": universe_code,
                "pg_universe_id": pg_universe_id,
                "market": market,
                "synced_at": _utc_now(),
            }
            self._write(data)

    def get_snapshot(self, snapshot_id: str) -> SnapshotRef:
        data = self._read()
        raw = data["snapshots"].get(snapshot_id)
        if not raw:
            raise KeyError(f"snapshot not found: {snapshot_id}")
        items = [
            DataVersionRef(
                dataset_code=str(item.get("dataset_code") or ""),
                version=str(item.get("version") or ""),
                checksum=item.get("checksum"),
                r2_uri=item.get("path") or item.get("r2_uri"),
            )
            for item in (raw.get("items") or [])
        ]
        return SnapshotRef(snapshot_id=snapshot_id, items=items)

    def upsert_model(self, model: ModelDefinition) -> None:
        """登记 ModelDefinition（engine 等元数据）。"""
        with self._lock:
            data = self._read()
            data.setdefault("models", {})
            key = model.code
            existing = data["models"].get(key)
            payload = model.model_dump(mode="json")
            if existing is not None and existing != payload:
                raise ModelImmutabilityError(
                    f"model {key!r} metadata conflict; bump code or align definition"
                )
            data["models"][key] = payload
            self._write(data)

    def get_model(self, model_code: str) -> ModelDefinition:
        data = self._read()
        raw = (data.get("models") or {}).get(model_code)
        if not raw:
            raise KeyError(f"model not found: {model_code!r}")
        return ModelDefinition.model_validate(raw)

    def upsert_model_version(self, record: ModelVersionRecord) -> None:
        """登记 model_version；同 code@version 禁止改 config。"""
        with self._lock:
            data = self._read()
            data.setdefault("model_versions", {})
            key = f"{record.model_code}@{record.version}"
            existing = data["model_versions"].get(key)
            if existing is not None:
                _assert_model_version_immutable(existing, record)
                # 允许更新 artifact_id / metrics（训练产物）
                merged = dict(existing)
                merged.update(record.model_dump(mode="json"))
                data["model_versions"][key] = merged
            else:
                data["model_versions"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_model_version(self, model_version_ref: str) -> ModelVersionRecord:
        code, version = _split_ref(model_version_ref)
        data = self._read()
        raw = (data.get("model_versions") or {}).get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"model_version not found: {model_version_ref}")
        return ModelVersionRecord.model_validate(raw)

    def upsert_artifact(self, record: ArtifactRecord) -> None:
        """登记 artifact 索引（内容寻址 id）。"""
        with self._lock:
            data = self._read()
            data.setdefault("artifacts", {})
            existing = data["artifacts"].get(record.artifact_id)
            if existing is not None and existing != record.model_dump(mode="json"):
                raise ValueError(f"artifact_id conflict: {record.artifact_id!r}")
            data["artifacts"][record.artifact_id] = record.model_dump(mode="json")
            self._write(data)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        data = self._read()
        raw = (data.get("artifacts") or {}).get(artifact_id)
        if not raw:
            raise KeyError(f"artifact not found: {artifact_id!r}")
        return ArtifactRecord.model_validate(raw)

    def upsert_experiment(self, experiment: ExperimentDefinition) -> None:
        with self._lock:
            data = self._read()
            data.setdefault("experiments", {})
            data["experiments"][experiment.experiment_id] = experiment.model_dump(mode="json")
            self._write(data)

    def get_experiment(self, experiment_id: str) -> ExperimentDefinition:
        data = self._read()
        raw = (data.get("experiments") or {}).get(experiment_id)
        if not raw:
            raise KeyError(f"experiment not found: {experiment_id!r}")
        return ExperimentDefinition.model_validate(raw)

    def upsert_signal_run(self, record: SignalRunRecord) -> None:
        """登记一次 Signal 管线运行（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("signal_runs", {})
            data["signal_runs"][record.signal_run_id] = record.model_dump(mode="json")
            self._write(data)

    def get_signal_run(self, signal_run_id: str) -> SignalRunRecord:
        data = self._read()
        raw = (data.get("signal_runs") or {}).get(signal_run_id)
        if not raw:
            raise KeyError(f"signal_run not found: {signal_run_id!r}")
        return SignalRunRecord.model_validate(raw)

    def upsert_consistency_run(self, record: ConsistencyRunRecord) -> None:
        """登记一次双引擎一致性运行（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("consistency_runs", {})
            data["consistency_runs"][record.run_id] = record.model_dump(mode="json")
            self._write(data)

    def get_consistency_run(self, run_id: str) -> ConsistencyRunRecord:
        data = self._read()
        raw = (data.get("consistency_runs") or {}).get(run_id)
        if not raw:
            raise KeyError(f"consistency_run not found: {run_id!r}")
        return ConsistencyRunRecord.model_validate(raw)

    def upsert_factor_dataset(self, record: FactorDatasetRecord) -> None:
        """登记 Factor Dataset 索引（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("factor_datasets", {})
            data["factor_datasets"][record.factor_dataset_id] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_factor_dataset(self, factor_dataset_id: str) -> FactorDatasetRecord:
        data = self._read()
        raw = (data.get("factor_datasets") or {}).get(factor_dataset_id)
        if not raw:
            raise KeyError(f"factor_dataset not found: {factor_dataset_id!r}")
        return FactorDatasetRecord.model_validate(raw)

    def upsert_evaluation_dataset(self, record: EvaluationDatasetRecord) -> None:
        """登记 Evaluation Dataset 索引（Local JSON）。"""
        with self._lock:
            data = self._read()
            data.setdefault("evaluation_datasets", {})
            data["evaluation_datasets"][record.evaluation_hash] = record.model_dump(
                mode="json"
            )
            self._write(data)

    def get_evaluation_dataset(self, evaluation_hash: str) -> EvaluationDatasetRecord:
        data = self._read()
        raw = (data.get("evaluation_datasets") or {}).get(evaluation_hash)
        if not raw:
            raise KeyError(f"evaluation_dataset not found: {evaluation_hash!r}")
        return EvaluationDatasetRecord.model_validate(raw)

    def upsert_factor_evaluation_summary(
        self, record: FactorEvaluationSummary
    ) -> None:
        """登记 IC Summary（Local JSON；key = metric_hash:horizon）。"""
        key = f"{record.metric_hash}:{int(record.horizon)}"
        with self._lock:
            data = self._read()
            data.setdefault("factor_evaluation_summaries", {})
            data["factor_evaluation_summaries"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_evaluation_summary(
        self, metric_hash: str, horizon: int
    ) -> FactorEvaluationSummary:
        data = self._read()
        key = f"{metric_hash}:{int(horizon)}"
        raw = (data.get("factor_evaluation_summaries") or {}).get(key)
        if not raw:
            raise KeyError(
                f"factor_evaluation_summary not found: {metric_hash!r} h={horizon}"
            )
        return FactorEvaluationSummary.model_validate(raw)

    def upsert_factor_group_evaluation(
        self, record: GroupEvaluationSummary
    ) -> None:
        """登记 Group Evaluation Summary（Local JSON）。"""
        key = f"{record.group_evaluation_hash}:{int(record.horizon)}"
        with self._lock:
            data = self._read()
            data.setdefault("factor_group_evaluations", {})
            data["factor_group_evaluations"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_group_evaluation(
        self, group_evaluation_hash: str, horizon: int
    ) -> GroupEvaluationSummary:
        data = self._read()
        key = f"{group_evaluation_hash}:{int(horizon)}"
        raw = (data.get("factor_group_evaluations") or {}).get(key)
        if not raw:
            raise KeyError(
                f"factor_group_evaluation not found: {group_evaluation_hash!r} h={horizon}"
            )
        return GroupEvaluationSummary.model_validate(raw)

    def upsert_factor_stability_evaluation(
        self, record: FactorStabilitySummary
    ) -> None:
        """登记 Stability Summary（Local JSON）。"""
        key = f"{record.stability_hash}:{int(record.horizon)}"
        with self._lock:
            data = self._read()
            data.setdefault("factor_stability_evaluations", {})
            data["factor_stability_evaluations"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_stability_evaluation(
        self, stability_hash: str, horizon: int
    ) -> FactorStabilitySummary:
        data = self._read()
        key = f"{stability_hash}:{int(horizon)}"
        raw = (data.get("factor_stability_evaluations") or {}).get(key)
        if not raw:
            raise KeyError(
                f"factor_stability_evaluation not found: {stability_hash!r} h={horizon}"
            )
        return FactorStabilitySummary.model_validate(raw)

    def upsert_factor_neutralization(
        self, record: FactorNeutralizationSummary
    ) -> None:
        """登记 Neutralization Summary（Local JSON）。"""
        key = record.neutralization_hash
        with self._lock:
            data = self._read()
            data.setdefault("factor_neutralizations", {})
            data["factor_neutralizations"][key] = record.model_dump(mode="json")
            self._write(data)

    def get_factor_neutralization(
        self, neutralization_hash: str
    ) -> FactorNeutralizationSummary:
        data = self._read()
        raw = (data.get("factor_neutralizations") or {}).get(neutralization_hash)
        if not raw:
            raise KeyError(
                f"factor_neutralization not found: {neutralization_hash!r}"
            )
        return FactorNeutralizationSummary.model_validate(raw)


class D1ResearchRegistry:
    """经 Worker 写入 qd_research。"""

    def upsert_data_version(
        self,
        *,
        dataset_code: str,
        version: str,
        schema_version: str,
        status: str,
        checksum: str,
        r2_uri: str,
        row_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        d1_client.query(
            """
            INSERT INTO data_version (
              dataset_code, version, schema_version, status, row_count,
              checksum, r2_uri, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dataset_code, version) DO UPDATE SET
              schema_version=excluded.schema_version,
              status=excluded.status,
              row_count=excluded.row_count,
              checksum=excluded.checksum,
              r2_uri=excluded.r2_uri,
              metadata_json=excluded.metadata_json
            """,
            [
                dataset_code,
                version,
                schema_version,
                status,
                row_count,
                checksum,
                r2_uri,
                json.dumps(metadata or {}, ensure_ascii=False),
                _utc_now(),
            ],
        )
        rows = d1_client.query(
            "SELECT data_version_id FROM data_version WHERE dataset_code=? AND version=?",
            [dataset_code, version],
        )
        return int(rows[0]["data_version_id"])

    def create_snapshot(
        self,
        *,
        snapshot_id: str,
        name: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        d1_client.query(
            """
            INSERT INTO data_snapshot (snapshot_id, name, created_at, metadata_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
              name=excluded.name,
              metadata_json=excluded.metadata_json
            """,
            [snapshot_id, name, _utc_now(), json.dumps(metadata or {}, ensure_ascii=False)],
        )
        for item in items:
            dv_id = item.get("data_version_id")
            if dv_id is None:
                raise ValueError("snapshot item requires data_version_id for D1 registry")
            d1_client.query(
                """
                INSERT INTO data_snapshot_item (snapshot_id, data_version_id, path, checksum)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_id, data_version_id) DO UPDATE SET
                  path=excluded.path,
                  checksum=excluded.checksum
                """,
                [snapshot_id, int(dv_id), item.get("path") or "", item.get("checksum")],
            )
        return snapshot_id

    def upsert_dataset(
        self, definition: DatasetDefinition, *, status: str = "ACTIVE"
    ) -> None:
        """登记 Dataset；status 文本列可写 validated（不改 DDL）。"""
        d1_client.query(
            """
            INSERT INTO dataset (
              code, version, name, frequency, universe_code, universe_version,
              snapshot_id, schema_version, definition_json, price_policy_json,
              status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, version) DO UPDATE SET
              name=excluded.name,
              frequency=excluded.frequency,
              universe_code=excluded.universe_code,
              universe_version=excluded.universe_version,
              snapshot_id=excluded.snapshot_id,
              schema_version=excluded.schema_version,
              definition_json=excluded.definition_json,
              price_policy_json=excluded.price_policy_json,
              status=excluded.status
            """,
            [
                definition.code,
                definition.version,
                definition.name,
                definition.frequency,
                definition.universe_code,
                definition.universe_version,
                definition.snapshot_id,
                definition.schema_version,
                json.dumps(definition.model_dump(mode="json"), ensure_ascii=False),
                json.dumps(definition.price_policy.model_dump(mode="json"), ensure_ascii=False),
                status,
                _utc_now(),
            ],
        )

    def get_dataset(self, dataset_ref: str) -> DatasetHandle:
        code, version = _split_ref(dataset_ref)
        rows = d1_client.query(
            "SELECT * FROM dataset WHERE code=? AND version=?",
            [code, version],
        )
        if not rows:
            raise KeyError(f"dataset not found: {dataset_ref}")
        row = rows[0]
        definition = DatasetDefinition.model_validate(json.loads(row["definition_json"]))
        # 覆盖可能漂移的 registry 列
        definition = definition.model_copy(
            update={
                "code": row["code"],
                "version": row["version"],
                "snapshot_id": row.get("snapshot_id") or definition.snapshot_id,
                "price_policy": PricePolicy.model_validate(
                    json.loads(row.get("price_policy_json") or "{}")
                ),
            }
        )
        snapshot = self.get_snapshot(definition.snapshot_id)
        digest = compute_dataset_hash(
            dataset_definition=definition.model_dump(mode="json"),
            dataset_version=definition.version,
            snapshot_id=definition.snapshot_id,
            schema_version=definition.schema_version,
            processor_version=definition.processor or "",
            materializer_version="none",
            price_policy=definition.price_policy.model_dump(mode="json"),
        )
        return DatasetHandle(
            definition=definition,
            snapshot=snapshot,
            dataset_hash=digest,
            manifest_uri="",
        )

    def upsert_feature(self, feature: FeatureDefinition) -> None:
        """登记 Feature/Factor 到 D1；写 feature_dependency；同版本不可变。"""
        from app.services.research_data.factor_lab.dependencies import (
            format_dependency,
            parse_dependencies,
        )
        from app.services.research_data.factor_lab.hash import compute_factor_hash
        from app.services.research_data.factor_lab.immutability import (
            FeatureImmutabilityError as _FIE,
            assert_feature_immutable,
            ensure_factor_hash,
        )

        feat = ensure_factor_hash(feature)
        feat = feat.model_copy(update={"factor_hash": compute_factor_hash(feat)})
        existing_rows = d1_client.query(
            "SELECT * FROM feature WHERE code=? AND version=?",
            [feat.code, feat.version],
        )
        if existing_rows:
            old = self.get_feature(f"{feat.code}@{feat.version}")
            try:
                assert_feature_immutable(old, feat)
            except _FIE as exc:
                raise FeatureImmutabilityError(str(exc)) from exc
            return

        # definition_json 保留扩展字段快照（兼容旧列）
        def_blob = dict(feat.definition or {})
        def_blob.update(
            {
                "description": feat.description,
                "factor_type": feat.factor_type,
                "computation_engine": feat.computation_engine,
                "engine_version": feat.engine_version,
                "universe": feat.universe,
                "information_policy": feat.information_policy,
                "schema_version": feat.schema_version,
                "factor_hash": feat.factor_hash,
                "processor_ref": feat.processor_ref,
                "price_policy": (
                    feat.price_policy.model_dump(mode="json")
                    if feat.price_policy
                    else None
                ),
                "dependencies": list(feat.dependencies or []),
            }
        )
        d1_client.query(
            """
            INSERT INTO feature (
              code, version, name, expression, frequency, definition_json,
              backend, online_supported, status, created_at,
              description, factor_type, computation_engine, engine_version,
              universe, information_policy, schema_version, factor_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                feat.code,
                feat.version,
                feat.name,
                feat.expression,
                feat.frequency,
                json.dumps(def_blob, ensure_ascii=False),
                feat.backend,
                1 if feat.online_supported else 0,
                _utc_now(),
                feat.description or "",
                feat.factor_type,
                feat.computation_engine,
                feat.engine_version or "",
                feat.universe,
                feat.information_policy,
                feat.schema_version,
                feat.factor_hash,
            ],
        )
        rows = d1_client.query(
            "SELECT feature_id FROM feature WHERE code=? AND version=?",
            [feat.code, feat.version],
        )
        if not rows:
            return
        feature_id = rows[0]["feature_id"]
        d1_client.query(
            "DELETE FROM feature_dependency WHERE feature_id=?",
            [feature_id],
        )
        for dep in parse_dependencies(feat.dependencies or []):
            d1_client.query(
                """
                INSERT INTO feature_dependency
                  (feature_id, dependency_type, dependency_code)
                VALUES (?, ?, ?)
                """,
                [feature_id, dep.dependency_type, dep.dependency_code],
            )
            # 规范化字符串写入 definition 侧已由 parse 保证
            _ = format_dependency(dep)

    def get_feature(self, feature_ref: str) -> FeatureDefinition:
        code, version = _split_ref(feature_ref)
        rows = d1_client.query(
            "SELECT * FROM feature WHERE code=? AND version=?",
            [code, version],
        )
        if not rows:
            raise KeyError(f"feature not found: {feature_ref}")
        row = rows[0]
        blob = json.loads(row.get("definition_json") or "{}")
        dep_rows = d1_client.query(
            """
            SELECT dependency_type, dependency_code
            FROM feature_dependency
            WHERE feature_id=?
            """,
            [row["feature_id"]],
        )
        deps_from_table = [
            f"{r['dependency_type']}:{r['dependency_code']}" for r in (dep_rows or [])
        ]
        deps = deps_from_table or list(blob.get("dependencies") or [])
        pp = blob.get("price_policy")
        price_policy = PricePolicy.model_validate(pp) if pp else None
        return FeatureDefinition(
            code=row["code"],
            version=row["version"],
            name=row["name"],
            expression=row["expression"],
            frequency=row["frequency"],
            backend=row.get("backend") or "r2_factor",
            online_supported=bool(row.get("online_supported")),
            definition={
                k: v
                for k, v in blob.items()
                if k
                not in {
                    "description",
                    "factor_type",
                    "computation_engine",
                    "engine_version",
                    "universe",
                    "information_policy",
                    "schema_version",
                    "factor_hash",
                    "processor_ref",
                    "price_policy",
                    "dependencies",
                }
            },
            dependencies=deps,
            description=row.get("description") or blob.get("description") or "",
            factor_type=row.get("factor_type") or blob.get("factor_type") or "CUSTOM",
            computation_engine=row.get("computation_engine")
            or blob.get("computation_engine")
            or "quantdinger",
            engine_version=row.get("engine_version")
            or blob.get("engine_version")
            or "",
            universe=row.get("universe") or blob.get("universe"),
            information_policy=row.get("information_policy")
            or blob.get("information_policy")
            or "UNKNOWN",
            schema_version=row.get("schema_version")
            or blob.get("schema_version")
            or "factor_daily_long@1",
            factor_hash=row.get("factor_hash") or blob.get("factor_hash"),
            price_policy=price_policy,
            processor_ref=blob.get("processor_ref"),
        )

    def upsert_processor(self, processor: ProcessorDefinition) -> None:
        """登记 Processor 到 D1；同 code@version 禁止改 pipeline。"""
        rows = d1_client.query(
            "SELECT definition_json FROM processor WHERE code=? AND version=?",
            [processor.code, processor.version],
        )
        if rows:
            existing = json.loads(rows[0]["definition_json"] or "{}")
            _assert_processor_immutable(existing, processor)
            return
        d1_client.query(
            """
            INSERT INTO processor (code, version, definition_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                processor.code,
                processor.version,
                json.dumps(processor.model_dump(mode="json"), ensure_ascii=False),
                _utc_now(),
            ],
        )

    def get_processor(self, processor_ref: str) -> ProcessorDefinition:
        """从 D1 读取 Processor。"""
        code, version = _split_ref(processor_ref)
        rows = d1_client.query(
            "SELECT * FROM processor WHERE code=? AND version=?",
            [code, version],
        )
        if not rows:
            raise KeyError(f"processor not found: {processor_ref}")
        raw = json.loads(rows[0]["definition_json"])
        return ProcessorDefinition.model_validate(raw)

    def upsert_model(self, model: ModelDefinition) -> None:
        d1_client.query(
            """
            INSERT INTO model (code, name, engine, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) DO NOTHING
            """,
            [model.code, model.name, model.engine, _utc_now()],
        )

    def get_model(self, model_code: str) -> ModelDefinition:
        rows = d1_client.query("SELECT * FROM model WHERE code=?", [model_code])
        if not rows:
            raise KeyError(f"model not found: {model_code!r}")
        row = rows[0]
        return ModelDefinition(
            code=row["code"],
            version="1",
            name=row["name"],
            engine=row["engine"],
            config={},
        )

    def upsert_model_version(self, record: ModelVersionRecord) -> None:
        self.upsert_model(
            ModelDefinition(
                code=record.model_code,
                version=record.version,
                name=record.model_code,
                engine="lightgbm",
                config=record.config,
            )
        )
        rows = d1_client.query(
            """
            SELECT mv.model_version_id FROM model_version mv
            JOIN model m ON m.model_id = mv.model_id
            WHERE m.code=? AND mv.version=?
            """,
            [record.model_code, record.version],
        )
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
        if rows:
            d1_client.query(
                """
                UPDATE model_version SET config_json=?, artifact_id=?, metrics_json=?
                WHERE model_version_id=?
                """,
                [
                    payload,
                    record.artifact_id,
                    json.dumps(record.metrics or {}, ensure_ascii=False),
                    rows[0]["model_version_id"],
                ],
            )
            return
        model_rows = d1_client.query(
            "SELECT model_id FROM model WHERE code=?", [record.model_code]
        )
        d1_client.query(
            """
            INSERT INTO model_version (
              model_id, version, config_json, artifact_id, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                model_rows[0]["model_id"],
                record.version,
                payload,
                record.artifact_id,
                json.dumps(record.metrics or {}, ensure_ascii=False),
                _utc_now(),
            ],
        )

    def get_model_version(self, model_version_ref: str) -> ModelVersionRecord:
        code, version = _split_ref(model_version_ref)
        rows = d1_client.query(
            """
            SELECT mv.config_json FROM model_version mv
            JOIN model m ON m.model_id = mv.model_id
            WHERE m.code=? AND mv.version=?
            """,
            [code, version],
        )
        if not rows:
            raise KeyError(f"model_version not found: {model_version_ref}")
        return ModelVersionRecord.model_validate(json.loads(rows[0]["config_json"]))

    def upsert_artifact(self, record: ArtifactRecord) -> None:
        d1_client.query(
            """
            INSERT INTO artifact (
              artifact_id, artifact_type, storage_uri, checksum, size_bytes,
              metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
              storage_uri=excluded.storage_uri,
              checksum=excluded.checksum,
              size_bytes=excluded.size_bytes,
              metadata_json=excluded.metadata_json
            """,
            [
                record.artifact_id,
                record.artifact_type,
                record.storage_uri,
                record.checksum,
                record.size_bytes,
                json.dumps(record.metadata or {}, ensure_ascii=False),
                _utc_now(),
            ],
        )

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        rows = d1_client.query(
            "SELECT * FROM artifact WHERE artifact_id=?", [artifact_id]
        )
        if not rows:
            raise KeyError(f"artifact not found: {artifact_id!r}")
        row = rows[0]
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            artifact_type=row["artifact_type"],
            storage_uri=row["storage_uri"],
            checksum=row.get("checksum"),
            size_bytes=row.get("size_bytes"),
            metadata=json.loads(row.get("metadata_json") or "{}"),
        )

    def upsert_experiment(self, experiment: ExperimentDefinition) -> None:
        """写入 D1 experiment；扩展字段塞进 parameters_json 以便回填。"""
        params = dict(experiment.parameters or {})
        params.update(
            {
                "dataset_ref": experiment.dataset_ref,
                "model_version_ref": experiment.model_version_ref,
                "processor_ref": experiment.processor_ref,
                "strategy_version": experiment.strategy_version,
                "manifest_uri": experiment.manifest_uri,
                "repro_fingerprint": experiment.repro_fingerprint,
                "bundle_hash": experiment.bundle_hash,
                "prediction_fingerprint": experiment.prediction_fingerprint,
                "model_artifact_id": experiment.model_artifact_id,
                "signal_artifact_id": experiment.signal_artifact_id,
                "signal_run_id": experiment.signal_run_id,
                "feature_refs": experiment.feature_refs,
                "segments": experiment.segments,
                "status": experiment.status,
            }
        )
        d1_client.query(
            """
            INSERT INTO experiment (
              experiment_id, name, snapshot_id, dataset_hash, status,
              mlflow_run_id, parameters_json, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(experiment_id) DO UPDATE SET
              metrics_json=excluded.metrics_json,
              mlflow_run_id=excluded.mlflow_run_id,
              parameters_json=excluded.parameters_json,
              status=excluded.status
            """,
            [
                experiment.experiment_id,
                experiment.name,
                experiment.snapshot_id,
                experiment.dataset_hash,
                experiment.status or "COMPLETED",
                experiment.mlflow_run_id,
                json.dumps(params, ensure_ascii=False),
                json.dumps(experiment.metrics or {}, ensure_ascii=False),
                _utc_now(),
            ],
        )

    def get_experiment(self, experiment_id: str) -> ExperimentDefinition:
        rows = d1_client.query(
            "SELECT * FROM experiment WHERE experiment_id=?", [experiment_id]
        )
        if not rows:
            raise KeyError(f"experiment not found: {experiment_id!r}")
        row = rows[0]
        params = json.loads(row.get("parameters_json") or "{}")
        metrics = json.loads(row.get("metrics_json") or "{}")
        return ExperimentDefinition(
            experiment_id=row["experiment_id"],
            name=row["name"],
            dataset_ref=str(params.get("dataset_ref") or row.get("dataset_ref") or ""),
            snapshot_id=row.get("snapshot_id") or "",
            dataset_hash=row.get("dataset_hash") or "",
            model_version_ref=params.get("model_version_ref"),
            mlflow_run_id=row.get("mlflow_run_id"),
            parameters=params,
            feature_refs=list(params.get("feature_refs") or []),
            processor_ref=params.get("processor_ref"),
            strategy_version=params.get("strategy_version"),
            model_artifact_id=params.get("model_artifact_id"),
            signal_artifact_id=params.get("signal_artifact_id"),
            signal_run_id=params.get("signal_run_id"),
            bundle_hash=params.get("bundle_hash"),
            prediction_fingerprint=params.get("prediction_fingerprint"),
            repro_fingerprint=params.get("repro_fingerprint"),
            metrics=metrics if isinstance(metrics, dict) else {},
            manifest_uri=str(params.get("manifest_uri") or ""),
            status=row.get("status") or params.get("status") or "COMPLETED",
            segments=dict(params.get("segments") or {}),
        )

    def upsert_signal_run(self, record: SignalRunRecord) -> None:
        """D1 无独立 signal_run 表；Phase 2E 索引仅 Local JSON，远端依赖 signal artifact。

        pipeline 已调用 upsert_artifact(type=signal)；此处不重复写入以免覆盖类型。
        """
        _ = record
        return

    def get_signal_run(self, signal_run_id: str) -> SignalRunRecord:
        """从 signal artifact 元数据重建（D1 无独立表）。"""
        art = self.get_artifact(signal_run_id)
        meta = dict(art.metadata or {})
        return SignalRunRecord(
            signal_run_id=signal_run_id,
            strategy_version=str(meta.get("strategy_version") or ""),
            prediction_fingerprint=str(meta.get("prediction_fingerprint") or ""),
            artifact_id=str(meta.get("artifact_id") or art.artifact_id),
            storage_uri=art.storage_uri,
            cash_weight=float(meta.get("cash_weight") or 0.0),
            metadata=meta,
        )

    def upsert_consistency_run(self, record: ConsistencyRunRecord) -> None:
        """D1 无独立表：索引落在 consistency artifact metadata（由 artifact_store 写入）。"""
        _ = record
        return

    def get_consistency_run(self, run_id: str) -> ConsistencyRunRecord:
        """从 consistency artifact 元数据重建。"""
        art = self.get_artifact(run_id)
        meta = dict(art.metadata or {})
        return ConsistencyRunRecord(
            run_id=run_id,
            dataset_hash=str(meta.get("dataset_hash") or ""),
            qlib_result_id=meta.get("qlib_result_id"),
            qd_result_id=meta.get("qd_result_id"),
            status=meta.get("status") or "PASSED",
            max_equity_diff=(
                float(meta["max_equity_diff"])
                if meta.get("max_equity_diff") is not None
                else None
            ),
            max_position_diff=(
                float(meta["max_position_diff"])
                if meta.get("max_position_diff") is not None
                else None
            ),
            artifact_uri=art.storage_uri,
            level=str(meta.get("level") or ""),
            semantic_fingerprint=meta.get("semantic_fingerprint"),
            created_at=meta.get("created_at"),
            metadata=meta,
        )

    def upsert_factor_dataset(self, record: FactorDatasetRecord) -> None:
        """D1：优先写 factor_dataset 表；失败则依赖 artifact metadata。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_dataset (
                  factor_dataset_id, factor_ref, factor_hash, dataset_hash,
                  snapshot_id, universe_code, frequency, start_date, end_date,
                  storage_uri, checksum, row_count, layout, schema_version,
                  status, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(factor_dataset_id) DO UPDATE SET
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  row_count=excluded.row_count,
                  status=excluded.status,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.factor_dataset_id,
                    record.factor_ref,
                    record.factor_hash,
                    record.dataset_hash,
                    record.snapshot_id,
                    record.universe_code,
                    record.frequency,
                    record.start_date,
                    record.end_date,
                    record.storage_uri,
                    record.checksum,
                    record.row_count,
                    record.layout,
                    record.schema_version,
                    record.status,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            # 未跑 migration 时：仅靠 upsert_artifact(type=factor_dataset)
            return

    def get_factor_dataset(self, factor_dataset_id: str) -> FactorDatasetRecord:
        """从 factor_dataset 表或 artifact 元数据读取。"""
        try:
            rows = d1_client.query(
                "SELECT * FROM factor_dataset WHERE factor_dataset_id=?",
                [factor_dataset_id],
            )
        except Exception:
            rows = []
        if rows:
            row = rows[0]
            meta = json.loads(row.get("metadata_json") or "{}")
            return FactorDatasetRecord(
                factor_dataset_id=row["factor_dataset_id"],
                factor_ref=row["factor_ref"],
                factor_hash=row["factor_hash"],
                dataset_hash=row["dataset_hash"],
                snapshot_id=row["snapshot_id"],
                universe_code=row.get("universe_code") or "",
                frequency=row.get("frequency") or "1d",
                start_date=row.get("start_date") or "",
                end_date=row.get("end_date") or "",
                storage_uri=row.get("storage_uri") or "",
                checksum=row.get("checksum"),
                row_count=row.get("row_count"),
                layout=row.get("layout") or "long",
                schema_version=row.get("schema_version") or "factor_daily_long@1",
                status=row.get("status") or "ACTIVE",
                created_at=row.get("created_at"),
                metadata=meta if isinstance(meta, dict) else {},
            )
        art = self.get_artifact(factor_dataset_id)
        meta = dict(art.metadata or {})
        return FactorDatasetRecord(
            factor_dataset_id=factor_dataset_id,
            factor_ref=str(meta.get("factor_ref") or ""),
            factor_hash=str(meta.get("factor_hash") or ""),
            dataset_hash=str(meta.get("dataset_hash") or ""),
            snapshot_id=str(meta.get("snapshot_id") or ""),
            universe_code=str(meta.get("universe_code") or ""),
            storage_uri=art.storage_uri,
            checksum=art.checksum,
            layout=meta.get("layout") or "long",
            schema_version=str(meta.get("schema_version") or "factor_daily_long@1"),
            metadata=meta,
        )

    def upsert_evaluation_dataset(self, record: EvaluationDatasetRecord) -> None:
        """D1：写 evaluation_dataset 表；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO evaluation_dataset (
                  evaluation_hash, factor_dataset_id, factor_dataset_hash,
                  snapshot_id, universe_code, universe_version,
                  start_date, end_date, return_spec_json, price_policy_json,
                  evaluator_version, mode, storage_uri, checksum, row_count,
                  schema_version, status, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evaluation_hash) DO UPDATE SET
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  row_count=excluded.row_count,
                  status=excluded.status,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.evaluation_hash,
                    record.factor_dataset_id,
                    record.factor_dataset_hash,
                    record.snapshot_id,
                    record.universe_code,
                    record.universe_version,
                    record.start_date,
                    record.end_date,
                    json.dumps(record.return_spec or {}, ensure_ascii=False),
                    json.dumps(
                        record.price_policy.model_dump(mode="json")
                        if record.price_policy
                        else {},
                        ensure_ascii=False,
                    ),
                    record.evaluator_version,
                    record.mode,
                    record.storage_uri,
                    record.checksum,
                    record.row_count,
                    record.schema_version,
                    record.status,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_evaluation_dataset(self, evaluation_hash: str) -> EvaluationDatasetRecord:
        """从 evaluation_dataset 表或 artifact 元数据读取。"""
        try:
            rows = d1_client.query(
                "SELECT * FROM evaluation_dataset WHERE evaluation_hash=?",
                [evaluation_hash],
            )
        except Exception:
            rows = []
        if rows:
            row = rows[0]
            meta = json.loads(row.get("metadata_json") or "{}")
            pp_raw = json.loads(row.get("price_policy_json") or "{}")
            return EvaluationDatasetRecord(
                evaluation_hash=row["evaluation_hash"],
                factor_dataset_id=row["factor_dataset_id"],
                factor_dataset_hash=row["factor_dataset_hash"],
                snapshot_id=row["snapshot_id"],
                universe_code=row.get("universe_code") or "",
                universe_version=row.get("universe_version") or "",
                start_date=row.get("start_date") or "",
                end_date=row.get("end_date") or "",
                return_spec=json.loads(row.get("return_spec_json") or "{}"),
                price_policy=PricePolicy.model_validate(pp_raw) if pp_raw else None,
                evaluator_version=row.get("evaluator_version") or "qd_factor_eval@1",
                mode=row.get("mode") or "CROSS_SECTIONAL",
                storage_uri=row.get("storage_uri") or "",
                checksum=row.get("checksum"),
                row_count=row.get("row_count"),
                schema_version=row.get("schema_version") or "evaluation_panel@1",
                status=row.get("status") or "ACTIVE",
                created_at=row.get("created_at"),
                metadata=meta if isinstance(meta, dict) else {},
            )
        art = self.get_artifact(evaluation_hash)
        meta = dict(art.metadata or {})
        return EvaluationDatasetRecord(
            evaluation_hash=evaluation_hash,
            factor_dataset_id=str(meta.get("factor_dataset_id") or ""),
            factor_dataset_hash=str(meta.get("factor_dataset_hash") or ""),
            snapshot_id=str(meta.get("snapshot_id") or ""),
            universe_code=str(meta.get("universe_code") or ""),
            storage_uri=art.storage_uri,
            checksum=art.checksum,
            schema_version=str(meta.get("schema_version") or "evaluation_panel@1"),
            metadata=meta,
        )

    def upsert_factor_evaluation_summary(
        self, record: FactorEvaluationSummary
    ) -> None:
        """D1：写 factor_evaluation_summary；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_evaluation_summary (
                  metric_hash, horizon, evaluation_hash, factor_dataset_id,
                  mean_ic, median_ic, std_ic, min_ic, max_ic, ic_ir, ic_t_stat,
                  positive_ic_ratio, mean_rank_ic, median_rank_ic, std_rank_ic,
                  min_rank_ic, max_rank_ic, rank_ic_ir, rank_ic_t_stat,
                  positive_rank_ic_ratio, valid_day_count, total_day_count,
                  direction, metric_version, storage_uri, checksum,
                  created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(metric_hash, horizon) DO UPDATE SET
                  mean_ic=excluded.mean_ic,
                  mean_rank_ic=excluded.mean_rank_ic,
                  ic_ir=excluded.ic_ir,
                  rank_ic_ir=excluded.rank_ic_ir,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.metric_hash,
                    int(record.horizon),
                    record.evaluation_hash,
                    record.factor_dataset_id,
                    record.mean_ic,
                    record.median_ic,
                    record.std_ic,
                    record.min_ic,
                    record.max_ic,
                    record.ic_ir,
                    record.ic_t_stat,
                    record.positive_ic_ratio,
                    record.mean_rank_ic,
                    record.median_rank_ic,
                    record.std_rank_ic,
                    record.min_rank_ic,
                    record.max_rank_ic,
                    record.rank_ic_ir,
                    record.rank_ic_t_stat,
                    record.positive_rank_ic_ratio,
                    record.valid_day_count,
                    record.total_day_count,
                    record.direction,
                    record.metric_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_evaluation_summary(
        self, metric_hash: str, horizon: int
    ) -> FactorEvaluationSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_evaluation_summary
                WHERE metric_hash=? AND horizon=?
                """,
                [metric_hash, int(horizon)],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"factor_evaluation_summary not found: {metric_hash!r} h={horizon}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return FactorEvaluationSummary(
            metric_hash=row["metric_hash"],
            evaluation_hash=row["evaluation_hash"],
            factor_dataset_id=row.get("factor_dataset_id") or "",
            horizon=int(row["horizon"]),
            mean_ic=row.get("mean_ic"),
            median_ic=row.get("median_ic"),
            std_ic=row.get("std_ic"),
            min_ic=row.get("min_ic"),
            max_ic=row.get("max_ic"),
            ic_ir=row.get("ic_ir"),
            ic_t_stat=row.get("ic_t_stat"),
            positive_ic_ratio=row.get("positive_ic_ratio"),
            mean_rank_ic=row.get("mean_rank_ic"),
            median_rank_ic=row.get("median_rank_ic"),
            std_rank_ic=row.get("std_rank_ic"),
            min_rank_ic=row.get("min_rank_ic"),
            max_rank_ic=row.get("max_rank_ic"),
            rank_ic_ir=row.get("rank_ic_ir"),
            rank_ic_t_stat=row.get("rank_ic_t_stat"),
            positive_rank_ic_ratio=row.get("positive_rank_ic_ratio"),
            valid_day_count=int(row.get("valid_day_count") or 0),
            total_day_count=int(row.get("total_day_count") or 0),
            direction=row.get("direction") or "AUTO",
            metric_version=row.get("metric_version") or "qd_factor_metrics@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_factor_group_evaluation(
        self, record: GroupEvaluationSummary
    ) -> None:
        """D1：写 factor_group_evaluation；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_group_evaluation (
                  group_evaluation_hash, horizon, evaluation_hash, factor_dataset_id,
                  group_count, weighting_method, direction, portfolio_mode,
                  long_group, short_group,
                  mean_long_return, mean_short_return, mean_long_short_return,
                  mean_turnover, mean_estimated_cost, mean_net_long_short_return,
                  valid_day_count, total_day_count, group_version,
                  storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(group_evaluation_hash, horizon) DO UPDATE SET
                  mean_long_short_return=excluded.mean_long_short_return,
                  mean_turnover=excluded.mean_turnover,
                  mean_net_long_short_return=excluded.mean_net_long_short_return,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.group_evaluation_hash,
                    int(record.horizon),
                    record.evaluation_hash,
                    record.factor_dataset_id,
                    int(record.group_count),
                    record.weighting_method,
                    record.direction,
                    record.portfolio_mode,
                    int(record.long_group),
                    int(record.short_group),
                    record.mean_long_return,
                    record.mean_short_return,
                    record.mean_long_short_return,
                    record.mean_turnover,
                    record.mean_estimated_cost,
                    record.mean_net_long_short_return,
                    record.valid_day_count,
                    record.total_day_count,
                    record.group_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_group_evaluation(
        self, group_evaluation_hash: str, horizon: int
    ) -> GroupEvaluationSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_group_evaluation
                WHERE group_evaluation_hash=? AND horizon=?
                """,
                [group_evaluation_hash, int(horizon)],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"factor_group_evaluation not found: {group_evaluation_hash!r} h={horizon}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")
        return GroupEvaluationSummary(
            group_evaluation_hash=row["group_evaluation_hash"],
            evaluation_hash=row["evaluation_hash"],
            factor_dataset_id=row.get("factor_dataset_id") or "",
            horizon=int(row["horizon"]),
            group_count=int(row.get("group_count") or 10),
            weighting_method=row.get("weighting_method") or "EQUAL_WEIGHT",
            direction=row.get("direction") or "POSITIVE",
            portfolio_mode=row.get("portfolio_mode") or "BOTH",
            long_group=int(row.get("long_group") or 1),
            short_group=int(row.get("short_group") or 10),
            mean_long_return=row.get("mean_long_return"),
            mean_short_return=row.get("mean_short_return"),
            mean_long_short_return=row.get("mean_long_short_return"),
            mean_turnover=row.get("mean_turnover"),
            mean_estimated_cost=row.get("mean_estimated_cost"),
            mean_net_long_short_return=row.get("mean_net_long_short_return"),
            valid_day_count=int(row.get("valid_day_count") or 0),
            total_day_count=int(row.get("total_day_count") or 0),
            group_version=row.get("group_version") or "qd_factor_groups@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_factor_stability_evaluation(
        self, record: FactorStabilitySummary
    ) -> None:
        """D1：写 factor_stability_evaluation；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_stability_evaluation (
                  stability_hash, horizon, evaluation_hash, factor_dataset_id,
                  rolling_windows_json, decay_summary_json, regime_summary_json,
                  ic_stability_metrics_json, group_stability_metrics_json,
                  stability_version, storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(stability_hash, horizon) DO UPDATE SET
                  decay_summary_json=excluded.decay_summary_json,
                  regime_summary_json=excluded.regime_summary_json,
                  ic_stability_metrics_json=excluded.ic_stability_metrics_json,
                  group_stability_metrics_json=excluded.group_stability_metrics_json,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.stability_hash,
                    int(record.horizon),
                    record.evaluation_hash,
                    record.factor_dataset_id,
                    json.dumps(record.rolling_windows_json or [], ensure_ascii=False),
                    json.dumps(record.decay_summary_json or [], ensure_ascii=False),
                    json.dumps(record.regime_summary_json or [], ensure_ascii=False),
                    json.dumps(
                        record.ic_stability_metrics_json or {}, ensure_ascii=False
                    ),
                    json.dumps(
                        record.group_stability_metrics_json or {}, ensure_ascii=False
                    ),
                    record.stability_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_stability_evaluation(
        self, stability_hash: str, horizon: int
    ) -> FactorStabilitySummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_stability_evaluation
                WHERE stability_hash=? AND horizon=?
                """,
                [stability_hash, int(horizon)],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"factor_stability_evaluation not found: {stability_hash!r} h={horizon}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return FactorStabilitySummary(
            stability_hash=row["stability_hash"],
            evaluation_hash=row["evaluation_hash"],
            factor_dataset_id=row.get("factor_dataset_id") or "",
            horizon=int(row["horizon"]),
            rolling_windows_json=_loads("rolling_windows_json", []),
            decay_summary_json=_loads("decay_summary_json", []),
            regime_summary_json=_loads("regime_summary_json", []),
            ic_stability_metrics_json=_loads("ic_stability_metrics_json", {}),
            group_stability_metrics_json=_loads("group_stability_metrics_json", {}),
            stability_version=row.get("stability_version") or "qd_factor_stability@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_factor_neutralization(
        self, record: FactorNeutralizationSummary
    ) -> None:
        """D1：写 factor_neutralization；未 migration 时静默跳过。"""
        try:
            d1_client.query(
                """
                INSERT INTO factor_neutralization (
                  neutralization_hash, factor_dataset_id, factor_dataset_hash,
                  method, targets_json, r_squared_mean, diagnostics_json,
                  neutralized_factor_dataset_id, neutralization_version,
                  storage_uri, checksum, created_at, metadata_json
                ) VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(neutralization_hash) DO UPDATE SET
                  r_squared_mean=excluded.r_squared_mean,
                  diagnostics_json=excluded.diagnostics_json,
                  neutralized_factor_dataset_id=excluded.neutralized_factor_dataset_id,
                  storage_uri=excluded.storage_uri,
                  checksum=excluded.checksum,
                  metadata_json=excluded.metadata_json
                """,
                [
                    record.neutralization_hash,
                    record.factor_dataset_id,
                    record.factor_dataset_hash,
                    record.method,
                    json.dumps(record.targets_json or [], ensure_ascii=False),
                    record.r_squared_mean,
                    json.dumps(record.diagnostics_json or {}, ensure_ascii=False),
                    record.neutralized_factor_dataset_id,
                    record.neutralization_version,
                    record.storage_uri,
                    record.checksum,
                    record.created_at or _utc_now(),
                    json.dumps(record.metadata or {}, ensure_ascii=False),
                ],
            )
        except Exception:
            return

    def get_factor_neutralization(
        self, neutralization_hash: str
    ) -> FactorNeutralizationSummary:
        try:
            rows = d1_client.query(
                """
                SELECT * FROM factor_neutralization
                WHERE neutralization_hash=?
                """,
                [neutralization_hash],
            )
        except Exception:
            rows = []
        if not rows:
            raise KeyError(
                f"factor_neutralization not found: {neutralization_hash!r}"
            )
        row = rows[0]
        meta = json.loads(row.get("metadata_json") or "{}")

        def _loads(key: str, default):
            raw = row.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return FactorNeutralizationSummary(
            neutralization_hash=row["neutralization_hash"],
            factor_dataset_id=row["factor_dataset_id"],
            factor_dataset_hash=row.get("factor_dataset_hash") or "",
            method=row.get("method") or "REGRESSION",
            targets_json=_loads("targets_json", []),
            r_squared_mean=row.get("r_squared_mean"),
            diagnostics_json=_loads("diagnostics_json", {}),
            neutralized_factor_dataset_id=row.get("neutralized_factor_dataset_id")
            or "",
            neutralization_version=row.get("neutralization_version")
            or "qd_factor_neutralization@1",
            storage_uri=row.get("storage_uri") or "",
            checksum=row.get("checksum"),
            created_at=row.get("created_at"),
            metadata=meta if isinstance(meta, dict) else {},
        )

    def upsert_universe_ref(
        self,
        *,
        universe_code: str,
        pg_universe_id: int | None,
        market: str | None,
    ) -> None:
        d1_client.query(
            """
            INSERT INTO universe_ref (universe_code, pg_universe_id, market, synced_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(universe_code) DO UPDATE SET
              pg_universe_id=excluded.pg_universe_id,
              market=excluded.market,
              synced_at=excluded.synced_at
            """,
            [universe_code, pg_universe_id, market, _utc_now()],
        )

    def get_snapshot(self, snapshot_id: str) -> SnapshotRef:
        rows = d1_client.query(
            """
            SELECT i.path, i.checksum, v.dataset_code, v.version, v.r2_uri
            FROM data_snapshot_item i
            JOIN data_version v ON v.data_version_id = i.data_version_id
            WHERE i.snapshot_id = ?
            """,
            [snapshot_id],
        )
        if not rows:
            # 允许空 items 但仍要求 snapshot 行存在
            head = d1_client.query(
                "SELECT snapshot_id FROM data_snapshot WHERE snapshot_id=?",
                [snapshot_id],
            )
            if not head:
                raise KeyError(f"snapshot not found: {snapshot_id}")
        items = [
            DataVersionRef(
                dataset_code=str(r.get("dataset_code") or ""),
                version=str(r.get("version") or ""),
                checksum=r.get("checksum"),
                r2_uri=r.get("path") or r.get("r2_uri"),
            )
            for r in rows
        ]
        return SnapshotRef(snapshot_id=snapshot_id, items=items)


def get_default_registry(root: Path | None = None) -> ResearchRegistry:
    """已配置 D1 Research 则用远端，否则本地 JSON。"""
    if d1_client.configured():
        return D1ResearchRegistry()
    return LocalJsonRegistry(root=root)


def new_snapshot_id(prefix: str = "snap") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _split_ref(ref: str) -> tuple[str, str]:
    text = str(ref or "").strip()
    if "@" not in text:
        raise ValueError(f"ref must be code@version, got {ref!r}")
    code, version = text.split("@", 1)
    if not code or not version:
        raise ValueError(f"ref must be code@version, got {ref!r}")
    return code, version
