"""Universe 来自 Snapshot。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument


def test_instruments_subset_of_snapshot(golden_qlib_env):
    query = golden_qlib_env["query"]
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    handle = query.dataset(ref)
    members = set(
        query.universe(
            handle.definition.universe_code,
            date(2024, 3, 1),
            snapshot_id=handle.definition.snapshot_id,
            universe_version=handle.definition.universe_version,
        )
    )
    result = mat.materialize(ref)
    qlib_ids = {
        ln.split("\t")[0]
        for ln in (Path(result.cache_path) / "instruments" / "all.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    }
    expected = {to_qlib_instrument(ik).lower() for ik in members}
    assert qlib_ids == expected
