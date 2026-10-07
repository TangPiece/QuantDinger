"""TrainingInputManifest 构建与校验。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .hashing import compute_input_manifest_hash
from .protocol import PartitionEntry, ReproducibilityInject, TrainingInputManifest


def build_input_manifest(
    *,
    dataset_hash: str = "",
    snapshot_id: str = "",
    partitions: Sequence[Mapping[str, Any]] | None = None,
    schema_hash: str = "",
    row_count: int = 0,
    min_event_time: str = "",
    max_event_time: str = "",
    inject: ReproducibilityInject | None = None,
) -> TrainingInputManifest:
    parts_raw = list(partitions or [])
    if inject and inject.known_partitions:
        parts_raw = list(inject.known_partitions)
    if not parts_raw and dataset_hash:
        # stub single logical partition for hash-only datasets
        parts_raw = [
            {
                "uri": f"qd/canonical/dataset/{dataset_hash[:16]}/part-000.parquet",
                "checksum": dataset_hash if len(dataset_hash) >= 32 else ("d" * 64),
                "rows": int(row_count or 0),
            }
        ]
    parts = [PartitionEntry.model_validate(p) for p in parts_raw]
    total_rows = int(row_count or sum(p.rows for p in parts))
    man = TrainingInputManifest(
        dataset_hash=dataset_hash,
        snapshot_id=snapshot_id,
        partitions=parts,
        schema_hash=schema_hash or (dataset_hash[:32] if dataset_hash else ""),
        row_count=total_rows,
        min_event_time=min_event_time,
        max_event_time=max_event_time,
    )
    h = compute_input_manifest_hash(man.model_dump(mode="json"))
    return man.model_copy(update={"input_manifest_hash": h})


def verify_input_manifest(
    expected: TrainingInputManifest,
    actual: TrainingInputManifest,
) -> list[str]:
    reasons: list[str] = []
    if expected.dataset_hash and actual.dataset_hash != expected.dataset_hash:
        reasons.append("dataset_hash_mismatch")
    if expected.snapshot_id and actual.snapshot_id != expected.snapshot_id:
        reasons.append("snapshot_id_mismatch")
    if expected.schema_hash and actual.schema_hash != expected.schema_hash:
        reasons.append("schema_hash_mismatch")
    if expected.row_count and actual.row_count and expected.row_count != actual.row_count:
        reasons.append("row_count_mismatch")
    exp_parts = {
        (p.uri, p.checksum): p.rows for p in expected.partitions
    }
    act_parts = {
        (p.uri, p.checksum): p.rows for p in actual.partitions
    }
    if exp_parts and act_parts != exp_parts:
        # distinguish data vs input
        same_uris = {u for u, _ in exp_parts} == {u for u, _ in act_parts}
        if same_uris:
            reasons.append("partition_checksum_mismatch")
        else:
            reasons.append("partition_set_mismatch")
    if (
        expected.input_manifest_hash
        and actual.input_manifest_hash
        and expected.input_manifest_hash != actual.input_manifest_hash
    ):
        if "partition_checksum_mismatch" not in reasons and "partition_set_mismatch" not in reasons:
            reasons.append("input_manifest_hash_mismatch")
    return reasons


__all__ = ["build_input_manifest", "verify_input_manifest"]
