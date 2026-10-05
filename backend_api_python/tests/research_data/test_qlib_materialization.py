"""Materialize 主路径：READY + 字段齐全。"""

from __future__ import annotations

from app.services.research_data.qlib_materializer.protocol import MaterializationStatus


def test_materialize_ready_fields(golden_qlib_env):
    mat = golden_qlib_env["materializer"]
    result = mat.materialize(golden_qlib_env["dataset_ref"], skip_qlib_validate=False)
    assert result.status == MaterializationStatus.READY
    assert result.dataset_hash
    assert result.materialization_id
    assert result.cache_path
    assert result.manifest_path
    assert result.checksum
    assert result.instrument_count == 3
    assert result.calendar_count >= 1
    assert result.feature_count >= 1
    assert result.cache_hit is False
    assert result.materializer_version.startswith("qlib_materializer@")
