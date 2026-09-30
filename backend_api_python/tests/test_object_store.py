"""object_store facade and path mapping unit tests."""
from __future__ import annotations

import pytest

from app.services.level2_ingest import config, object_store

FTYPE = "逐笔成交"
HANGQING = "行情"


def test_object_key_matches_r2_key():
    assert config.object_key("20260818", "600460.SH", FTYPE) == config.r2_key(
        "20260818", "600460.SH", FTYPE
    )


def test_date_hierarchy():
    assert config.date_hierarchy("20260506") == "2026/202605/20260506"


def test_baidu_path_has_year_month_day():
    p = config.baidu_path("20260506", "600460.SH", HANGQING)
    assert p.startswith("/apps/")
    assert p.endswith(f"{HANGQING}.parquet")
    assert p == (
        f"/apps/{config.BAIDU_APP_NAME}/l2/2026/202605/20260506/"
        f"600460.SH/{HANGQING}.parquet"
    )


def test_baidu_path_from_logical_key_nests_date():
    key = f"l2/20260506/600460.SH/{FTYPE}.parquet"
    assert config.baidu_path_from_key(key) == (
        f"/apps/{config.BAIDU_APP_NAME}/l2/2026/202605/20260506/"
        f"600460.SH/{FTYPE}.parquet"
    )


def test_logical_baidu_rel_roundtrip():
    key = f"l2/20260506/000001.SZ/{FTYPE}.parquet"
    rel = config.logical_key_to_baidu_rel(key)
    assert rel == f"l2/2026/202605/20260506/000001.SZ/{FTYPE}.parquet"
    assert config.baidu_rel_to_logical_key(rel) == key


def test_catalog_and_manifest_keys_not_rewritten():
    cat = "l2/_catalog/baidu/20260506.parquet"
    man = "l2/_manifests/20260506.parquet"
    assert config.logical_key_to_baidu_rel(cat) == cat
    assert config.logical_key_to_baidu_rel(man) == man
    assert config.baidu_path_from_key(cat) == f"/apps/{config.BAIDU_APP_NAME}/{cat}"
    assert config.baidu_path_from_key(man) == f"/apps/{config.BAIDU_APP_NAME}/{man}"


def test_backend_defaults_r2(monkeypatch):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "r2")
    assert object_store.backend() == "r2"


def test_read_backend_baidu(monkeypatch):
    monkeypatch.setattr(config, "STORAGE_READ", "baidu")
    assert object_store.read_backend() == "baidu"


def test_invalid_backend_raises():
    with pytest.raises(ValueError):
        object_store._norm("s3")  # noqa: SLF001
