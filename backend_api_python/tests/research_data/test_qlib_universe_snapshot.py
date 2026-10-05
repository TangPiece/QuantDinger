"""Universe 来自 Snapshot。"""

from __future__ import annotations

from pathlib import Path

from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument


def test_instruments_subset_of_snapshot(golden_qlib_env):
    """物化 instruments ≡ DQ.universe(dataset_end as_of)。"""
    query = golden_qlib_env["query"]
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    handle = query.dataset(ref)
    # 必须与 Materializer 窗口终点一致（禁止用任意中间日）
    as_of = golden_qlib_env["end"]
    members = set(
        query.universe(
            handle.definition.universe_code,
            as_of,
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
    assert "CNStock:688001" in members
