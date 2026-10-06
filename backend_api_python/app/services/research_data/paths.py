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


def evaluation_stability_prefix(
    *, stability_hash: str, kind: str, year: int | None = None, month: int | None = None
) -> str:
    """Phase 4F：``qd/evaluation/stability/{hash}/{kind}/[year=/month=]``。"""
    base = f"{_root()}/evaluation/stability/{stability_hash}/{kind}"
    if year is None or month is None:
        return base
    return f"{base}/year={int(year):04d}/month={int(month):02d}"


def evaluation_stability_key(
    *,
    stability_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
    part: str = "part-000.parquet",
) -> str:
    """分区 kind 带 year/month；decay/regime 可无年月。"""
    if year is None or month is None:
        return f"{evaluation_stability_prefix(stability_hash=stability_hash, kind=kind)}/{part}"
    return (
        f"{evaluation_stability_prefix(stability_hash=stability_hash, kind=kind, year=year, month=month)}"
        f"/{part}"
    )


def evaluation_stability_manifest_key(*, stability_hash: str) -> str:
    return f"{_root()}/evaluation/stability/{stability_hash}/manifest.json"


def evaluation_stability_summary_key(*, stability_hash: str) -> str:
    return f"{_root()}/evaluation/stability/{stability_hash}/summary.json"


def neutralized_factor_prefix(
    *,
    neutralization_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
) -> str:
    """Phase 4G：``qd/factor/neutralized/{hash}/{kind}/[year=/month=]``。"""
    base = f"{_root()}/factor/neutralized/{neutralization_hash}/{kind}"
    if year is None or month is None:
        return base
    return f"{base}/year={int(year):04d}/month={int(month):02d}"


def neutralized_factor_key(
    *,
    neutralization_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
    part: str = "part-000.parquet",
) -> str:
    if year is None or month is None:
        return f"{neutralized_factor_prefix(neutralization_hash=neutralization_hash, kind=kind)}/{part}"
    return (
        f"{neutralized_factor_prefix(neutralization_hash=neutralization_hash, kind=kind, year=year, month=month)}"
        f"/{part}"
    )


def neutralized_factor_manifest_key(*, neutralization_hash: str) -> str:
    return f"{_root()}/factor/neutralized/{neutralization_hash}/manifest.json"


def neutralized_factor_summary_key(*, neutralization_hash: str) -> str:
    return f"{_root()}/factor/neutralized/{neutralization_hash}/summary.json"


def combined_factor_prefix(
    *,
    combination_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
) -> str:
    """Phase 4H：``qd/factor/combined/{hash}/{kind}/[year=/month=]``。"""
    base = f"{_root()}/factor/combined/{combination_hash}/{kind}"
    if year is None or month is None:
        return base
    return f"{base}/year={int(year):04d}/month={int(month):02d}"


def combined_factor_key(
    *,
    combination_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
    part: str = "part-000.parquet",
) -> str:
    if year is None or month is None:
        return f"{combined_factor_prefix(combination_hash=combination_hash, kind=kind)}/{part}"
    return (
        f"{combined_factor_prefix(combination_hash=combination_hash, kind=kind, year=year, month=month)}"
        f"/{part}"
    )


def combined_factor_manifest_key(*, combination_hash: str) -> str:
    return f"{_root()}/factor/combined/{combination_hash}/manifest.json"


def combined_factor_summary_key(*, combination_hash: str) -> str:
    return f"{_root()}/factor/combined/{combination_hash}/summary.json"


def factor_portfolio_prefix(
    *,
    portfolio_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
) -> str:
    """Phase 4I：``qd/portfolio/{hash}/{kind}/[year=/month=]``。"""
    base = f"{_root()}/portfolio/{portfolio_hash}/{kind}"
    if year is None or month is None:
        return base
    return f"{base}/year={int(year):04d}/month={int(month):02d}"


def factor_portfolio_key(
    *,
    portfolio_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
    part: str = "part-000.parquet",
) -> str:
    if year is None or month is None:
        return f"{factor_portfolio_prefix(portfolio_hash=portfolio_hash, kind=kind)}/{part}"
    return (
        f"{factor_portfolio_prefix(portfolio_hash=portfolio_hash, kind=kind, year=year, month=month)}"
        f"/{part}"
    )


def factor_portfolio_manifest_key(*, portfolio_hash: str) -> str:
    return f"{_root()}/portfolio/{portfolio_hash}/manifest.json"


def factor_portfolio_summary_key(*, portfolio_hash: str) -> str:
    return f"{_root()}/portfolio/{portfolio_hash}/summary.json"


def factor_portfolio_metrics_key(*, portfolio_hash: str) -> str:
    return f"{_root()}/portfolio/{portfolio_hash}/metrics/summary.json"


def strategy_research_prefix(
    *,
    strategy_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
) -> str:
    """Phase 5A：``qd/strategy/{hash}/{kind}/[year=/month=]``。"""
    base = f"{_root()}/strategy/{strategy_hash}/{kind}"
    if year is None or month is None:
        return base
    return f"{base}/year={int(year):04d}/month={int(month):02d}"


def strategy_research_key(
    *,
    strategy_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
    part: str = "part-000.parquet",
) -> str:
    if year is None or month is None:
        return f"{strategy_research_prefix(strategy_hash=strategy_hash, kind=kind)}/{part}"
    return (
        f"{strategy_research_prefix(strategy_hash=strategy_hash, kind=kind, year=year, month=month)}"
        f"/{part}"
    )


def strategy_research_manifest_key(*, strategy_hash: str) -> str:
    return f"{_root()}/strategy/{strategy_hash}/manifest.json"


def strategy_research_summary_key(*, strategy_hash: str) -> str:
    return f"{_root()}/strategy/{strategy_hash}/summary.json"


def strategy_research_snapshot_key(*, strategy_hash: str) -> str:
    return f"{_root()}/strategy/{strategy_hash}/snapshots/strategy_spec.json"


def research_backtest_prefix(
    *,
    backtest_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
) -> str:
    """Phase 5B：``qd/backtest/{hash}/{kind}/[year=/month=]``。"""
    base = f"{_root()}/backtest/{backtest_hash}/{kind}"
    if year is None or month is None:
        return base
    return f"{base}/year={int(year):04d}/month={int(month):02d}"


def research_backtest_key(
    *,
    backtest_hash: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
    part: str = "part-000.parquet",
) -> str:
    if year is None or month is None:
        return f"{research_backtest_prefix(backtest_hash=backtest_hash, kind=kind)}/{part}"
    return (
        f"{research_backtest_prefix(backtest_hash=backtest_hash, kind=kind, year=year, month=month)}"
        f"/{part}"
    )


def research_backtest_manifest_key(*, backtest_hash: str) -> str:
    return f"{_root()}/backtest/{backtest_hash}/manifest.json"


def research_backtest_summary_key(*, backtest_hash: str) -> str:
    return f"{_root()}/backtest/{backtest_hash}/summary.json"


def research_backtest_metrics_key(*, backtest_hash: str) -> str:
    return f"{_root()}/backtest/{backtest_hash}/metrics/summary.json"


def qlib_run_prefix(*, qlib_run_hash: str, kind: str = "") -> str:
    """Phase 5D：``qd/qlib_run/{hash}/[kind]``。"""
    base = f"{_root()}/qlib_run/{qlib_run_hash}"
    if kind:
        return f"{base}/{kind}"
    return base


def qlib_run_manifest_key(*, qlib_run_hash: str) -> str:
    return f"{qlib_run_prefix(qlib_run_hash=qlib_run_hash)}/manifest.json"


def qlib_run_summary_key(*, qlib_run_hash: str) -> str:
    return f"{qlib_run_prefix(qlib_run_hash=qlib_run_hash)}/summary.json"


def qlib_run_metrics_key(*, qlib_run_hash: str) -> str:
    return f"{qlib_run_prefix(qlib_run_hash=qlib_run_hash)}/metrics/summary.json"


def qlib_run_compatibility_key(*, qlib_run_hash: str) -> str:
    return f"{qlib_run_prefix(qlib_run_hash=qlib_run_hash)}/compatibility.json"


def qlib_run_nav_key(*, qlib_run_hash: str) -> str:
    """Phase 5D/5E：日频 NAV 曲线。"""
    return f"{qlib_run_prefix(qlib_run_hash=qlib_run_hash)}/nav/daily.json"


def cross_validation_prefix(*, cv_hash: str, kind: str = "") -> str:
    """Phase 5E：``qd/cross_validation/{cv_hash}/[kind]``。"""
    base = f"{_root()}/cross_validation/{cv_hash}"
    if kind:
        return f"{base}/{kind}"
    return base


def cross_validation_manifest_key(*, cv_hash: str) -> str:
    return f"{cross_validation_prefix(cv_hash=cv_hash)}/manifest.json"


def cross_validation_report_key(*, cv_hash: str) -> str:
    return f"{cross_validation_prefix(cv_hash=cv_hash)}/report.json"


def cross_validation_attribution_key(*, cv_hash: str) -> str:
    return f"{cross_validation_prefix(cv_hash=cv_hash)}/attribution.json"


def production_bundle_prefix(*, bundle_hash: str, kind: str = "") -> str:
    """Phase 5F：``qd/production/bundles/{bundle_hash}/[kind]``。"""
    base = f"{_root()}/production/bundles/{bundle_hash}"
    if kind:
        return f"{base}/{kind}"
    return base


def production_bundle_manifest_key(*, bundle_hash: str) -> str:
    return f"{production_bundle_prefix(bundle_hash=bundle_hash)}/manifest.json"


def production_bundle_summary_key(*, bundle_hash: str) -> str:
    return f"{production_bundle_prefix(bundle_hash=bundle_hash)}/summary.json"


def production_run_prefix(*, run_id: str, kind: str = "") -> str:
    """Phase 5F：干跑 inference 产物。"""
    base = f"{_root()}/production/runs/{run_id}"
    if kind:
        return f"{base}/{kind}"
    return base


def production_runtime_prefix(*, runtime_id: str, kind: str = "") -> str:
    """Phase 6A：``qd/production/runtime/{runtime_id}/[kind]``。"""
    base = f"{_root()}/production/runtime/{runtime_id}"
    if kind:
        return f"{base}/{kind}"
    return base


def production_runtime_manifest_key(*, runtime_id: str) -> str:
    return f"{production_runtime_prefix(runtime_id=runtime_id)}/manifest.json"


def production_runtime_run_key(*, runtime_id: str, run_id: str) -> str:
    return f"{production_runtime_prefix(runtime_id=runtime_id)}/runs/{run_id}/inference.json"


def production_portfolio_prefix(
    *, account_id: str, year: int | None = None, month: int | None = None, day: int | None = None
) -> str:
    """Phase 6B：``qd/production/portfolio/account={id}/[year=/month=/day=/]``。"""
    base = f"{_root()}/production/portfolio/account={account_id}"
    if year is not None:
        base = f"{base}/year={int(year):04d}"
    if month is not None:
        base = f"{base}/month={int(month):02d}"
    if day is not None:
        base = f"{base}/day={int(day):02d}"
    return base


def production_portfolio_snapshot_key(
    *, account_id: str, year: int, month: int, day: int, kind: str = "portfolio.parquet"
) -> str:
    return f"{production_portfolio_prefix(account_id=account_id, year=year, month=month, day=day)}/{kind}"


def production_portfolio_event_key(
    *, account_id: str, event_id: str, year: int, month: int, day: int
) -> str:
    return (
        f"{production_portfolio_prefix(account_id=account_id, year=year, month=month, day=day)}"
        f"/events/{event_id}.json"
    )


def production_risk_prefix(*, risk_run_id: str, kind: str = "") -> str:
    """Phase 6C：``qd/production/risk/{risk_run_id}/[kind]``。"""
    base = f"{_root()}/production/risk/{risk_run_id}"
    if kind:
        return f"{base}/{kind}"
    return base


def production_risk_snapshot_key(*, risk_run_id: str) -> str:
    return f"{production_risk_prefix(risk_run_id=risk_run_id)}/snapshot.json"


def production_risk_decision_key(*, risk_run_id: str) -> str:
    return f"{production_risk_prefix(risk_run_id=risk_run_id)}/decision.json"


def production_oms_prefix(*, order_id: str, kind: str = "") -> str:
    """Phase 6D：``qd/production/oms/{order_id}/[kind]``。"""
    base = f"{_root()}/production/oms/{order_id}"
    if kind:
        return f"{base}/{kind}"
    return base


def production_oms_order_key(*, order_id: str) -> str:
    return f"{production_oms_prefix(order_id=order_id)}/order.json"


def production_broker_adapter_prefix(
    *, broker_id: str, kind: str = ""
) -> str:
    """Phase 6E：``qd/production/broker/{broker_id}/[kind]``。"""
    base = f"{_root()}/production/broker/{broker_id}"
    if kind:
        return f"{base}/{kind}"
    return base


def production_broker_event_key(
    *,
    broker_id: str,
    year: str,
    month: str,
    day: str,
    event_id: str,
) -> str:
    """``qd/production/broker/{broker_id}/events/{yyyy}/{mm}/{dd}/{event_id}.json``。"""
    return (
        f"{production_broker_adapter_prefix(broker_id=broker_id, kind='events')}"
        f"/{year}/{month}/{day}/{event_id}.json"
    )


def r2_uri(key: str, *, bucket: str | None = None) -> str:
    """逻辑 URI：r2://{bucket}/{key}。"""
    from app.services.level2_ingest import config as l2_config

    b = bucket or l2_config.R2_BUCKET or "quantdinger-data"
    return f"r2://{b}/{key.lstrip('/')}"
