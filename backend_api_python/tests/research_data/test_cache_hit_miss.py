"""CachingCanonicalStore：miss → hit → 删缓存 → miss，再从 remote 重建。"""

from __future__ import annotations

from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.canonical_store import CachingCanonicalStore, LocalCanonicalStore


def test_cache_miss_hit_invalidate_miss(tmp_path):
    remote = LocalCanonicalStore(root=tmp_path / "remote")
    local = LocalCanonicalStore(root=tmp_path / "local")
    cache = CachingCanonicalStore(remote=remote, local=local)

    key = "qd/canonical/market/daily/exchange=CN/year=2024/month=05/part-000.parquet"
    payload = b"parquet-bytes-fixture"
    remote.put_bytes(key, payload)

    cache.reset_stats()
    assert cache.stats() == {"hits": 0, "misses": 0}

    # miss
    assert cache.get_bytes(key) == payload
    assert cache.stats()["misses"] == 1
    assert cache.stats()["hits"] == 0
    assert local.exists(key)

    # hit
    assert cache.get_bytes(key) == payload
    assert cache.stats()["hits"] == 1
    assert cache.stats()["misses"] == 1

    # 删本地 → 再 miss → 从 remote 重建
    cache.invalidate(key)
    assert not local.exists(key)
    assert cache.get_bytes(key) == payload
    assert cache.stats()["misses"] == 2
    assert local.exists(key)

    # Repository materialize 也应计入 hit（已在 local）；显式 materialize_root 避免写 home
    repo = CanonicalRepository(cache, materialize_root=tmp_path / "duck")
    before_hits = cache.hits
    path = repo.materialize_path(key)
    assert path.is_file()
    assert cache.hits == before_hits + 1
