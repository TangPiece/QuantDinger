"""R2 / 本地研究对象键规范（docs/data/phase1/03_r2_layout.md）。"""

from __future__ import annotations

from . import config


def _root() -> str:
    return config.canonical_prefix()


def market_daily_prefix(*, exchange: str, year: int, month: int) -> str:
    """日线 partition 前缀。"""
    return (
        f"{_root()}/canonical/market/daily/"
        f"exchange={exchange}/year={int(year):04d}/month={int(month):02d}"
    )


def market_daily_key(*, exchange: str, year: int, month: int, part: str = "part-000.parquet") -> str:
    return f"{market_daily_prefix(exchange=exchange, year=year, month=month)}/{part}"


def pit_fundamental_prefix(*, exchange: str, year: int) -> str:
    return f"{_root()}/canonical/fundamental/pit/exchange={exchange}/year={int(year):04d}"


def pit_fundamental_key(*, exchange: str, year: int, part: str = "part-000.parquet") -> str:
    return f"{pit_fundamental_prefix(exchange=exchange, year=year)}/{part}"


def universe_snapshot_prefix(*, universe_code: str, universe_version: str) -> str:
    return f"{_root()}/canonical/universe/code={universe_code}/version={universe_version}"


def universe_snapshot_key(
    *,
    universe_code: str,
    universe_version: str,
    part: str = "part-000.parquet",
) -> str:
    return f"{universe_snapshot_prefix(universe_code=universe_code, universe_version=universe_version)}/{part}"


def corporate_action_prefix(*, exchange: str, year: int) -> str:
    return f"{_root()}/canonical/corporate_action/exchange={exchange}/year={int(year):04d}"


def trading_status_prefix(*, exchange: str, year: int, month: int) -> str:
    return (
        f"{_root()}/canonical/trading_status/"
        f"exchange={exchange}/year={int(year):04d}/month={int(month):02d}"
    )


def factor_daily_prefix(*, factor_set: str, year: int, month: int) -> str:
    return (
        f"{_root()}/factor/daily/factor_set={factor_set}/"
        f"year={int(year):04d}/month={int(month):02d}"
    )


def factor_daily_key(
    *,
    factor_set: str,
    year: int,
    month: int,
    part: str = "part-000.parquet",
) -> str:
    return f"{factor_daily_prefix(factor_set=factor_set, year=year, month=month)}/{part}"


def snapshot_manifest_key(snapshot_id: str) -> str:
    return f"{_root()}/snapshot/{snapshot_id}/manifest.json"


def dataset_manifest_key(*, dataset_code: str, dataset_version: str, snapshot_id: str) -> str:
    return f"{_root()}/dataset/{dataset_code}/{dataset_version}/{snapshot_id}/manifest.json"


def r2_uri(key: str, *, bucket: str | None = None) -> str:
    """逻辑 URI：r2://{bucket}/{key}。"""
    from app.services.level2_ingest import config as l2_config

    b = bucket or l2_config.R2_BUCKET or "quantdinger-data"
    return f"r2://{b}/{key.lstrip('/')}"
