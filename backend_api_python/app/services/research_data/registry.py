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
    DataVersionRef,
    DatasetDefinition,
    DatasetHandle,
    ExperimentDefinition,
    FeatureDefinition,
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
        with self._lock:
            data = self._read()
            data["features"][f"{feature.code}@{feature.version}"] = feature.model_dump(mode="json")
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
        d1_client.query(
            """
            INSERT INTO feature (
              code, version, name, expression, frequency, definition_json,
              backend, online_supported, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
            ON CONFLICT(code, version) DO UPDATE SET
              name=excluded.name,
              expression=excluded.expression,
              frequency=excluded.frequency,
              definition_json=excluded.definition_json,
              backend=excluded.backend,
              online_supported=excluded.online_supported,
              status='ACTIVE'
            """,
            [
                feature.code,
                feature.version,
                feature.name,
                feature.expression,
                feature.frequency,
                json.dumps(feature.definition, ensure_ascii=False),
                feature.backend,
                1 if feature.online_supported else 0,
                _utc_now(),
            ],
        )

    def get_feature(self, feature_ref: str) -> FeatureDefinition:
        code, version = _split_ref(feature_ref)
        rows = d1_client.query(
            "SELECT * FROM feature WHERE code=? AND version=?",
            [code, version],
        )
        if not rows:
            raise KeyError(f"feature not found: {feature_ref}")
        row = rows[0]
        return FeatureDefinition(
            code=row["code"],
            version=row["version"],
            name=row["name"],
            expression=row["expression"],
            frequency=row["frequency"],
            backend=row.get("backend") or "r2_factor",
            online_supported=bool(row.get("online_supported")),
            definition=json.loads(row.get("definition_json") or "{}"),
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
