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
    DataVersionRef,
    DatasetDefinition,
    DatasetHandle,
    FeatureDefinition,
    PricePolicy,
    SnapshotRef,
)
from .hashing import compute_dataset_hash


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

    def upsert_dataset(self, definition: DatasetDefinition) -> None: ...

    def get_dataset(self, dataset_ref: str) -> DatasetHandle: ...

    def upsert_feature(self, feature: FeatureDefinition) -> None: ...

    def get_feature(self, feature_ref: str) -> FeatureDefinition: ...

    def upsert_universe_ref(
        self,
        *,
        universe_code: str,
        pg_universe_id: int | None,
        market: str | None,
    ) -> None: ...

    def get_snapshot(self, snapshot_id: str) -> SnapshotRef: ...


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

    def upsert_dataset(self, definition: DatasetDefinition) -> None:
        with self._lock:
            data = self._read()
            key = f"{definition.code}@{definition.version}"
            data["datasets"][key] = definition.model_dump(mode="json")
            self._write(data)

    def get_dataset(self, dataset_ref: str) -> DatasetHandle:
        code, version = _split_ref(dataset_ref)
        data = self._read()
        raw = data["datasets"].get(f"{code}@{version}")
        if not raw:
            raise KeyError(f"dataset not found: {dataset_ref}")
        definition = DatasetDefinition.model_validate(raw)
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

    def upsert_dataset(self, definition: DatasetDefinition) -> None:
        d1_client.query(
            """
            INSERT INTO dataset (
              code, version, name, frequency, universe_code, universe_version,
              snapshot_id, schema_version, definition_json, price_policy_json,
              status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
            ON CONFLICT(code, version) DO UPDATE SET
              name=excluded.name,
              frequency=excluded.frequency,
              universe_code=excluded.universe_code,
              universe_version=excluded.universe_version,
              snapshot_id=excluded.snapshot_id,
              schema_version=excluded.schema_version,
              definition_json=excluded.definition_json,
              price_policy_json=excluded.price_policy_json,
              status='ACTIVE'
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
