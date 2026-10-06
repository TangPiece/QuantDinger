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


def corporate_action_key(*, exchange: str, year: int, part: str = "part-000.parquet") -> str:
    return f"{corporate_action_prefix(exchange=exchange, year=year)}/{part}"


def trading_status_prefix(*, exchange: str, year: int, month: int) -> str:
    return (
        f"{_root()}/canonical/trading_status/"
        f"exchange={exchange}/year={int(year):04d}/month={int(month):02d}"
    )


def trading_status_key(
    *, exchange: str, year: int, month: int, part: str = "part-000.parquet"
) -> str:
    return f"{trading_status_prefix(exchange=exchange, year=year, month=month)}/{part}"


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


def factor_dataset_manifest_key(*, factor_dataset_id: str) -> str:
    """Phase 4A：``qd/dataset/factor/{factor_dataset_id}/manifest.json``。"""
    return f"{_root()}/dataset/factor/{factor_dataset_id}/manifest.json"


def evaluation_factor_prefix(*, evaluation_hash: str, year: int, month: int) -> str:
    """Phase 4C：``qd/evaluation/factor/{hash}/year=/month=``。"""
    return (
        f"{_root()}/evaluation/factor/{evaluation_hash}/"
        f"year={int(year):04d}/month={int(month):02d}"
    )


def evaluation_factor_key(
    *,
    evaluation_hash: str,
    year: int,
    month: int,
    part: str = "part-000.parquet",
) -> str:
    return f"{evaluation_factor_prefix(evaluation_hash=evaluation_hash, year=year, month=month)}/{part}"


def evaluation_manifest_key(*, evaluation_hash: str) -> str:
    """Phase 4C：``qd/evaluation/factor/{evaluation_hash}/manifest.json``。"""
    return f"{_root()}/evaluation/factor/{evaluation_hash}/manifest.json"


def evaluation_metrics_ic_prefix(*, metric_hash: str, year: int, month: int) -> str:
    """Phase 4D：``qd/evaluation/metrics/{hash}/ic/year=/month=``。"""
    return (
        f"{_root()}/evaluation/metrics/{metric_hash}/ic/"
        f"year={int(year):04d}/month={int(month):02d}"
    )


def evaluation_metrics_ic_key(
    *,
    metric_hash: str,
    year: int,
    month: int,
    part: str = "part-000.parquet",
) -> str:
    return (
        f"{evaluation_metrics_ic_prefix(metric_hash=metric_hash, year=year, month=month)}"
        f"/{part}"
    )


def evaluation_metrics_manifest_key(*, metric_hash: str) -> str:
    """Phase 4D：``qd/evaluation/metrics/{metric_hash}/manifest.json``。"""
    return f"{_root()}/evaluation/metrics/{metric_hash}/manifest.json"


def evaluation_metrics_summary_key(*, metric_hash: str) -> str:
    return f"{_root()}/evaluation/metrics/{metric_hash}/summary.json"


def evaluation_groups_prefix(
    *, group_evaluation_hash: str, kind: str, year: int, month: int
) -> str:
    """Phase 4E：``qd/evaluation/groups/{hash}/{kind}/year=/month=``。"""
    return (
        f"{_root()}/evaluation/groups/{group_evaluation_hash}/{kind}/"
        f"year={int(year):04d}/month={int(month):02d}"
    )


def evaluation_groups_key(
    *,
    group_evaluation_hash: str,
    kind: str,
    year: int,
    month: int,
    part: str = "part-000.parquet",
) -> str:
    return (
        f"{evaluation_groups_prefix(group_evaluation_hash=group_evaluation_hash, kind=kind, year=year, month=month)}"
        f"/{part}"
    )


def evaluation_groups_manifest_key(*, group_evaluation_hash: str) -> str:
    return f"{_root()}/evaluation/groups/{group_evaluation_hash}/manifest.json"


def evaluation_groups_summary_key(*, group_evaluation_hash: str) -> str:
    return f"{_root()}/evaluation/groups/{group_evaluation_hash}/summary.json"


def r2_uri(key: str, *, bucket: str | None = None) -> str:
    """逻辑 URI：r2://{bucket}/{key}。"""
    from app.services.level2_ingest import config as l2_config

    b = bucket or l2_config.R2_BUCKET or "quantdinger-data"
    return f"r2://{b}/{key.lstrip('/')}"
