"""FeatureSet / Build 引用与 R2 键。"""

from __future__ import annotations

from app.services.research_data import config as rd_config
from app.services.research_data.paths import r2_uri


def split_ref(ref: str) -> tuple[str, str]:
    text = str(ref or "").strip()
    if "@" not in text:
        raise ValueError(f"invalid ref: {ref!r}")
    code, version = text.split("@", 1)
    if not code or not version:
        raise ValueError(f"invalid ref: {ref!r}")
    return code, version


def feature_set_ref(*, code: str, version: str) -> str:
    return f"{code}@{version}"


def feature_set_r2_key(*, code: str, version: str) -> str:
    root = rd_config.canonical_prefix()
    safe_code = str(code or "").replace("/", "_")
    safe_ver = str(version or "").replace("/", "_")
    return f"{root}/feature_set/{safe_code}/{safe_ver}/manifest.json"


def logical_feature_set_uri(*, code: str, version: str) -> str:
    return r2_uri(feature_set_r2_key(code=code, version=version))


def factor_build_index_key(
    *,
    factor_ref: str,
    dataset_hash: str,
    layout: str,
    start_date: str,
    end_date: str,
) -> str:
    """构建槽位键（本地镜像相对路径）。"""
    code, version = split_ref(factor_ref)
    safe_code = code.replace("/", "_")
    safe_ver = version.replace("/", "_")
    dh = str(dataset_hash or "")[:16]
    window = f"{start_date}_{end_date}".replace("/", "-")
    root = rd_config.canonical_prefix()
    return (
        f"{root}/feature_factor/build/factor/{safe_code}/{safe_ver}/"
        f"{dh}/{layout}/{window}/build_index.json"
    )


def feature_set_build_index_key(
    *,
    feature_set_ref: str,
    dataset_hash: str,
    layout: str,
    start_date: str,
    end_date: str,
) -> str:
    code, version = split_ref(feature_set_ref)
    safe_code = code.replace("/", "_")
    safe_ver = version.replace("/", "_")
    dh = str(dataset_hash or "")[:16]
    window = f"{start_date}_{end_date}".replace("/", "-")
    root = rd_config.canonical_prefix()
    return (
        f"{root}/feature_factor/build/feature_set/{safe_code}/{safe_ver}/"
        f"{dh}/{layout}/{window}/build_index.json"
    )


__all__ = [
    "factor_build_index_key",
    "feature_set_build_index_key",
    "feature_set_ref",
    "feature_set_r2_key",
    "logical_feature_set_uri",
    "split_ref",
]
