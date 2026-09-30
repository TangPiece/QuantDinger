"""catalog per-backend paths."""
from __future__ import annotations

from app.services.level2_ingest import config


def test_local_catalog_path_by_backend():
    assert config.local_catalog_path("20260818", backend="r2") == (
        config.CATALOG_DIR / "r2" / "20260818.parquet"
    )
    assert config.local_catalog_path("20260818", backend="baidu") == (
        config.CATALOG_DIR / "baidu" / "20260818.parquet"
    )


def test_catalog_object_key_by_backend():
    assert config.catalog_object_key("20260818", backend="r2") == (
        f"{config.R2_PREFIX}/_catalog/r2/20260818.parquet"
    )
    assert config.catalog_object_key("20260818", backend="baidu") == (
        f"{config.R2_PREFIX}/_catalog/baidu/20260818.parquet"
    )
