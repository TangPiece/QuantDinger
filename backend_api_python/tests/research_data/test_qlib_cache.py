"""Cache hit / wipe rebuild / 损坏 manifest / lock。"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.research_data.qlib_materializer import cache as cache_mod
from app.services.research_data.qlib_materializer.protocol import MaterializationStatus


def test_cache_hit_and_wipe_rebuild(golden_qlib_env):
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    first = mat.materialize(ref)
    second = mat.materialize(ref)
    assert second.cache_hit is True
    assert second.checksum == first.checksum

    cache_mod.invalidate(Path(first.cache_path))
    rebuilt = mat.materialize(ref, force=True)
    assert rebuilt.cache_hit is False
    assert rebuilt.status == MaterializationStatus.READY
    assert rebuilt.materialization_id == first.materialization_id
    assert rebuilt.checksum == first.checksum


def test_corrupt_manifest_triggers_rebuild(golden_qlib_env):
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    first = mat.materialize(ref)
    mani = Path(first.manifest_path)
    mani.write_text("{not-json", encoding="utf-8")
    assert cache_mod.is_ready_cache(Path(first.cache_path)) is False
    rebuilt = mat.materialize(ref)
    assert rebuilt.cache_hit is False
    assert rebuilt.status == MaterializationStatus.READY
    payload = json.loads(Path(rebuilt.manifest_path).read_text(encoding="utf-8"))
    assert payload["status"] == "READY"
