"""Instrument 映射稳定；PG 变更不影响。"""

from __future__ import annotations

from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument


def test_cnstock_mapping_rules():
    assert to_qlib_instrument("CNStock:600000") == "SH600000"
    assert to_qlib_instrument("CNStock:000001") == "SZ000001"
    assert to_qlib_instrument("CNStock:300750") == "SZ300750"


def test_instruments_immune_to_pg_monkeypatch(golden_qlib_env, monkeypatch):
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    first = mat.materialize(ref)
    before = sorted(
        ln.split("\t")[0]
        for ln in open(f"{first.cache_path}/instruments/all.txt", encoding="utf-8")
        if ln.strip()
    )

    class FakeUniverseService:
        def list_universes(self, *_a, **_k):
            return [{"id": 1, "code": "CSI300"}]

        def get_members(self, *_a, **_k):
            return [{"instrument_key": "CNStock:999999"}]

    monkeypatch.setattr("app.services.universe.UniverseService", FakeUniverseService, raising=True)
    second = mat.materialize(ref, force=True)
    after = sorted(
        ln.split("\t")[0]
        for ln in open(f"{second.cache_path}/instruments/all.txt", encoding="utf-8")
        if ln.strip()
    )
    assert after == before
    assert "sz999999" not in after
    assert all(x == x.lower() for x in after)
