"""fund_cn_basic@v1 — PIT revision, TTM/SQ, compute, coverage, catalog gates."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.data_query import DataQuery
from app.services.research_data.fund_cn.adapters.base import (
    AnnounceRow,
    ShareCapitalRow,
    StatementFieldRow,
)
from app.services.research_data.fund_cn.catalog import (
    FACTOR_DEFINITIONS,
    FACTOR_SET,
    backtest_eligible_factors,
    coverage_matrix,
    effective_factor,
    factor_ids,
    mvp_factors,
    promote_factor_to_pit_safe,
    schema_hash,
)
from app.services.research_data.fund_cn.compute import (
    MarketRequiredError,
    build_daily_factor_panel,
)
from app.services.research_data.fund_cn.coverage import (
    METRIC_TO_STATEMENT_FIELDS,
    coverage_summary,
    evaluate_metric_coverage,
    resolve_statement_fields,
)
from app.services.research_data.fund_cn.ingest import stage_from_adapters
from app.services.research_data.fund_cn.metrics import (
    attach_announce,
    compute_period_metrics,
    derive_fields,
    pivot_statements,
    statements_to_pit_metrics,
    to_single_quarter,
)
from app.services.research_data.fund_cn.orchestrator import run_pipeline
from app.services.research_data.fund_cn.register import to_feature
from app.services.research_data.factor_lab.dependencies import validate_for_backtest
from app.services.research_data.registry import LocalJsonRegistry


def _stmt(
    ik: str,
    period: date,
    field: str,
    value: float,
    *,
    statement_type: str = "income",
    q: int | None = None,
    revision: int = 0,
) -> StatementFieldRow:
    quarter = q if q is not None else (period.month - 1) // 3 + 1
    return StatementFieldRow(
        instrument_key=ik,
        report_period_end=period,
        report_period_start=None,
        fiscal_year=period.year,
        fiscal_quarter=quarter,
        statement_type=statement_type,
        field_code=field,
        value=value,
        source="test",
        source_record_id=f"{ik}:{period}:{field}:r{revision}",
        revision=revision,
    )


def _ann(ik: str, period: date, available: datetime, revision: int = 0) -> AnnounceRow:
    return AnnounceRow(
        instrument_key=ik,
        report_period_end=period,
        publish_time=available,
        available_time=available,
        revision=revision,
        is_restatement=revision > 0,
        source="test",
        source_record_id=f"{ik}:{period}:r{revision}",
    )


@pytest.fixture
def sample_universe() -> str:
    return "CNStock:000001"


def test_catalog_has_thirty_factors_and_mvp_subset():
    assert FACTOR_SET == "fund_cn_basic@v1"
    assert len(FACTOR_DEFINITIONS) == 30
    mvp = mvp_factors()
    assert len(mvp) >= 12
    assert all(f.enabled and f.information_policy == "PIT_SAFE" for f in mvp)
    assert schema_hash()
    matrix = coverage_matrix()
    assert len(matrix) == 30
    pcf = next(r for r in matrix if r["factor_id"] == "pcf")
    assert pcf["COMPUTE_OK"] == "ok"
    div = next(r for r in matrix if r["factor_id"] == "dividend_yield")
    assert div["COMPUTE_OK"] == "pending"


def test_mvp_features_pass_pit_backtest_gate():
    for factor in mvp_factors():
        feature = to_feature(factor)
        assert feature.information_policy == "PIT_SAFE"
        assert validate_for_backtest(feature)


def test_revision_snapshot_no_lookahead(sample_universe: str):
    """revision=0 keeps first-release value; later revision does not pollute it."""
    ik = sample_universe
    pe = date(2023, 12, 31)
    t0 = datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 4, 15, 10, 0, tzinfo=timezone.utc)
    statements = [
        _stmt(ik, pe, "net_profit_parent", 100.0, revision=0),
        _stmt(ik, pe, "shareholder_equity", 1000.0, statement_type="balance", revision=0),
        _stmt(ik, pe, "net_profit_parent", 120.0, revision=1),
        _stmt(ik, pe, "shareholder_equity", 1000.0, statement_type="balance", revision=1),
    ]
    announces = [_ann(ik, pe, t0, revision=0), _ann(ik, pe, t1, revision=1)]
    rows = statements_to_pit_metrics(
        pd.DataFrame([s.__dict__ for s in statements]),
        pd.DataFrame([a.__dict__ for a in announces]),
    )
    roe_rows = [r for r in rows if r["metric_code"] == "roe"]
    assert len(roe_rows) == 2
    by_rev = {r["revision"]: r for r in roe_rows}
    assert by_rev[0]["value"] == pytest.approx(0.1)
    assert by_rev[1]["value"] == pytest.approx(0.12)
    assert by_rev[0]["available_time"] == t0
    assert by_rev[1]["available_time"] == t1


def test_same_timestamp_revisions_emit_only_effective_snapshot(sample_universe: str):
    """同一时点没有 rev0 独立可见区间，只发布最高 revision 的有效快照。"""
    ik = sample_universe
    pe = date(2023, 12, 31)
    at = datetime(2024, 4, 15, 10, 0, tzinfo=timezone.utc)
    statements = [
        _stmt(ik, pe, "net_profit_parent", 100.0, revision=0),
        _stmt(ik, pe, "shareholder_equity", 1000.0, statement_type="balance", revision=0),
        _stmt(ik, pe, "net_profit_parent", 200.0, revision=1),
        _stmt(ik, pe, "shareholder_equity", 1000.0, statement_type="balance", revision=1),
    ]
    rows = statements_to_pit_metrics(
        pd.DataFrame([s.__dict__ for s in statements]),
        pd.DataFrame([_ann(ik, pe, at, 0).__dict__, _ann(ik, pe, at, 1).__dict__]),
    )
    roe_rows = [row for row in rows if row["metric_code"] == "roe"]
    assert len(roe_rows) == 1
    assert roe_rows[0]["revision"] == 1
    assert roe_rows[0]["value"] == pytest.approx(0.2)


def test_to_single_quarter_and_ttm(sample_universe: str):
    ik = sample_universe
    # YTD cumulatives: Q1=10, Q2=25, Q3=45, FY=100 → SQ 10,15,20,55; TTM@FY=100
    periods = [
        (date(2023, 3, 31), 1, 10.0),
        (date(2023, 6, 30), 2, 25.0),
        (date(2023, 9, 30), 3, 45.0),
        (date(2023, 12, 31), 4, 100.0),
    ]
    statements = []
    announces = []
    for pe, q, cum in periods:
        statements.append(_stmt(ik, pe, "revenue", cum, q=q))
        statements.append(_stmt(ik, pe, "net_profit_parent", cum / 10, q=q))
        statements.append(
            _stmt(ik, pe, "shareholder_equity", 200.0, statement_type="balance", q=q)
        )
        statements.append(
            _stmt(ik, pe, "shares_outstanding", 10.0, statement_type="balance", q=q)
        )
        announces.append(
            _ann(ik, pe, datetime(2023, pe.month, 28, 15, 0, tzinfo=timezone.utc))
        )
    wide = pivot_statements(pd.DataFrame([s.__dict__ for s in statements]))
    joined = attach_announce(wide, pd.DataFrame([a.__dict__ for a in announces]))
    sq = to_single_quarter(joined)
    fy = sq[sq["report_period_end"] == date(2023, 12, 31)].iloc[0]
    assert fy["revenue__sq"] == pytest.approx(55.0)
    assert fy["revenue__cum"] == pytest.approx(100.0)

    metrics = compute_period_metrics(joined)
    ttm = [
        r
        for r in metrics
        if r["metric_code"] == "revenue_ttm" and r["report_period_end"] == date(2023, 12, 31)
    ]
    assert ttm and ttm[0]["value"] == pytest.approx(100.0)


def test_pipeline_pit_visibility_and_restatement(tmp_path: Path, sample_universe: str):
    ik = sample_universe
    p2023 = date(2023, 12, 31)
    available = datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc)
    restated = datetime(2024, 4, 15, 10, 0, tzinfo=timezone.utc)

    def pack(pe: date, q: int, rev: int, revenue_cum: float, np_cum: float, equity: float):
        return [
            _stmt(ik, pe, "revenue", revenue_cum, q=q, revision=rev),
            _stmt(ik, pe, "net_profit_parent", np_cum, q=q, revision=rev),
            _stmt(ik, pe, "gross_profit", revenue_cum * 0.4, q=q, revision=rev),
            _stmt(ik, pe, "total_assets", equity * 2, statement_type="balance", q=q, revision=rev),
            _stmt(ik, pe, "total_liabilities", equity, statement_type="balance", q=q, revision=rev),
            _stmt(ik, pe, "shareholder_equity", equity, statement_type="balance", q=q, revision=rev),
            _stmt(ik, pe, "cash_from_operations", np_cum * 1.1, statement_type="cashflow", q=q, revision=rev),
            _stmt(ik, pe, "shares_outstanding", 10.0, statement_type="balance", q=q, revision=rev),
        ]

    statements = []
    # Prior year + 2023 quarters (cumulative) revision 0
    statements += pack(date(2022, 12, 31), 4, 0, 80.0, 8.0, 100.0)
    statements += pack(date(2023, 3, 31), 1, 0, 20.0, 2.0, 105.0)
    statements += pack(date(2023, 6, 30), 2, 0, 45.0, 5.0, 107.0)
    statements += pack(date(2023, 9, 30), 3, 0, 75.0, 7.5, 108.0)
    statements += pack(p2023, 4, 0, 100.0, 10.0, 110.0)
    # Restatement of FY2023
    statements += pack(p2023, 4, 1, 110.0, 12.0, 110.0)

    announces = [
        _ann(ik, date(2022, 12, 31), datetime(2023, 3, 30, 15, 0, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 3, 31), datetime(2023, 4, 28, 15, 0, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 6, 30), datetime(2023, 8, 28, 15, 0, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 9, 30), datetime(2023, 10, 28, 15, 0, tzinfo=timezone.utc)),
        _ann(ik, p2023, available, revision=0),
        _ann(ik, p2023, restated, revision=1),
    ]

    market = pd.DataFrame(
        [
            {"instrument_key": ik, "trading_date": date(2024, 4, 1), "close": 11.0},
            {"instrument_key": ik, "trading_date": date(2024, 4, 16), "close": 12.0},
        ]
    )

    store = LocalCanonicalStore(tmp_path / "canonical")
    registry = LocalJsonRegistry(tmp_path / "registry")
    result = run_pipeline(
        [ik],
        [date(2024, 3, 20), date(2024, 4, 1), date(2024, 4, 16)],
        statement_rows=statements,
        announce_rows=announces,
        share_capital_rows=[
            ShareCapitalRow(
                ik,
                date(2023, 12, 31),
                datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc),
                10.0,
                source="test",
            )
        ],
        market=market,
        root=tmp_path / "staging",
        store=store,
        registry=registry,
        mvp_only=True,
        register=True,
    )
    assert result["pit"]["row_count"] > 0
    assert result["factors"]["row_count"] > 0
    assert result["registered"]
    # 端到端读取已发布日面板，确认估值使用 staging 中的时点总股本。
    from app.services.research_data.canonical_repository import CanonicalRepository

    factor_keys = [day["storage_uri"] for day in result["factors"]["days"]]
    factor_panel = CanonicalRepository(store).read_parquet_df(keys=factor_keys)
    pe_by_day = dict(zip(factor_panel["trading_date"], factor_panel["pe_ttm"]))
    assert pe_by_day["2024-04-01"] == pytest.approx(11.0)
    assert pe_by_day["2024-04-16"] == pytest.approx(10.0)

    query = DataQuery(store, registry)
    mid = query.fundamental([ik], ["roe"], datetime(2024, 4, 1, 12, 0, tzinfo=timezone.utc), exchange="CN")
    assert not mid.empty
    assert abs(float(mid.iloc[0]["value"]) - (10.0 / 110.0)) < 1e-6
    assert int(mid.iloc[0]["revision"]) == 0

    after = query.fundamental([ik], ["roe"], datetime(2024, 4, 16, 12, 0, tzinfo=timezone.utc), exchange="CN")
    assert not after.empty
    assert int(after.iloc[0]["revision"]) == 1
    assert abs(float(after.iloc[0]["value"]) - (12.0 / 110.0)) < 1e-6


def test_coverage_requires_announce(tmp_path: Path, sample_universe: str):
    ik = sample_universe
    statements = [
        _stmt(ik, date(2023, 12, 31), "revenue", 100.0),
        _stmt(ik, date(2023, 12, 31), "net_profit_parent", 10.0),
        _stmt(ik, date(2023, 12, 31), "shareholder_equity", 100.0, statement_type="balance"),
        _stmt(ik, date(2023, 12, 31), "total_assets", 200.0, statement_type="balance"),
        _stmt(ik, date(2023, 12, 31), "total_liabilities", 100.0, statement_type="balance"),
        _stmt(ik, date(2023, 12, 31), "gross_profit", 40.0),
        _stmt(ik, date(2023, 12, 31), "cash_from_operations", 12.0, statement_type="cashflow"),
        _stmt(ik, date(2023, 12, 31), "shares_outstanding", 10.0, statement_type="balance"),
    ]
    stage_from_adapters(statements, [], root=tmp_path)
    from app.services.research_data.fund_cn.staging import read_announce_rows, read_statement_rows

    summary = coverage_summary(read_statement_rows(tmp_path), read_announce_rows(tmp_path))
    assert summary["eligible_count"] == 0


def test_coverage_announcement_must_match_revision(sample_universe: str):
    """rev1 没有自己的公告时不能借用 rev0 公告通过 PIT 门禁。"""
    ik = sample_universe
    pe = date(2023, 12, 31)
    statements = pd.DataFrame(
        [
            _stmt(ik, pe, "net_profit_parent", 10.0, revision=0).__dict__,
            _stmt(ik, pe, "net_profit_parent", 12.0, revision=1).__dict__,
        ]
    )
    announce = pd.DataFrame(
        [_ann(ik, pe, datetime(2024, 3, 28, 15, tzinfo=timezone.utc), revision=0).__dict__]
    )
    report = evaluate_metric_coverage(
        statements,
        announce,
        "net_profit_parent",
        max_missing_announce=0.0,
    )
    assert report.missing_announce_rate == pytest.approx(0.5)
    assert not report.pit_ok


def test_valuation_requires_market(sample_universe: str):
    ik = sample_universe
    available = datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc)
    pit_rows = [
        {
            "instrument_key": ik,
            "metric_code": "roe",
            "report_period_end": date(2023, 12, 31),
            "available_time": available,
            "revision": 0,
            "value": 0.1,
        }
    ]
    with pytest.raises(MarketRequiredError):
        build_daily_factor_panel(
            pit_rows,
            [date(2024, 4, 1)],
            [ik],
            market=None,
            mvp_only=True,
        )


def test_valuation_panel_uses_market_and_shares(sample_universe: str):
    ik = sample_universe
    available = datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc)
    pit_rows = [
        {
            "instrument_key": ik,
            "metric_code": "shares_outstanding",
            "report_period_end": date(2023, 12, 31),
            "available_time": available,
            "revision": 0,
            "value": 10.0,
        },
        {
            "instrument_key": ik,
            "metric_code": "shareholder_equity",
            "report_period_end": date(2023, 12, 31),
            "available_time": available,
            "revision": 0,
            "value": 100.0,
        },
        {
            "instrument_key": ik,
            "metric_code": "net_income_ttm",
            "report_period_end": date(2023, 12, 31),
            "available_time": available,
            "revision": 0,
            "value": 20.0,
        },
        {
            "instrument_key": ik,
            "metric_code": "revenue_ttm",
            "report_period_end": date(2023, 12, 31),
            "available_time": available,
            "revision": 0,
            "value": 200.0,
        },
        {
            "instrument_key": ik,
            "metric_code": "cash_from_operations_ttm",
            "report_period_end": date(2023, 12, 31),
            "available_time": available,
            "revision": 0,
            "value": 25.0,
        },
        {
            "instrument_key": ik,
            "metric_code": "roe",
            "report_period_end": date(2023, 12, 31),
            "available_time": available,
            "revision": 0,
            "value": 0.1,
        },
    ]
    market = pd.DataFrame([{"instrument_key": ik, "trading_date": date(2024, 4, 1), "close": 10.0}])
    panel = build_daily_factor_panel(
        pit_rows,
        [date(2024, 4, 1)],
        [ik],
        market,
        mvp_only=True,
    )
    assert len(panel) == 1
    assert abs(float(panel.iloc[0]["pb"]) - 1.0) < 1e-6
    assert abs(float(panel.iloc[0]["pe_ttm"]) - 5.0) < 1e-6
    assert abs(float(panel.iloc[0]["ps_ttm"]) - 0.5) < 1e-6
    assert abs(float(panel.iloc[0]["roe"]) - 0.1) < 1e-6


def test_promote_enables_backtest_eligibility():
    pending = next(f for f in FACTOR_DEFINITIONS if not f.mvp and f.factor_id == "operating_margin")
    before = {f.factor_id for f in backtest_eligible_factors()}
    assert pending.factor_id not in before
    updated = promote_factor_to_pit_safe(pending.factor_id)
    assert updated.all_gates_ok
    assert updated.enabled is True
    assert updated.information_policy == "PIT_SAFE"
    assert effective_factor(pending.factor_id).enabled is True
    assert pending.factor_id in {f.factor_id for f in backtest_eligible_factors()}


def test_metric_deps_all_mapped_in_field_map():
    deps = {d for f in FACTOR_DEFINITIONS for d in f.metric_deps}
    for dep in deps:
        fields = resolve_statement_fields(dep)
        assert fields
        assert dep in METRIC_TO_STATEMENT_FIELDS


def test_restatement_q4_sq_and_next_year_ttm(sample_universe: str):
    """智普 2.1: rev1 Q4 cum=650 → sq=250; FY2024 Q1 TTM=670."""
    ik = sample_universe
    # YTD: Q1=100, Q2=200, Q3=400, Q4_rev0=550 → SQ 100,100,200,150
    # Q4_rev1=650 → sq=650-400=250; Q1_2024=120 → TTM=100+200+250+120=670
    statements = [
        _stmt(ik, date(2023, 3, 31), "revenue", 100.0, q=1),
        _stmt(ik, date(2023, 6, 30), "revenue", 200.0, q=2),
        _stmt(ik, date(2023, 9, 30), "revenue", 400.0, q=3),
        _stmt(ik, date(2023, 12, 31), "revenue", 550.0, q=4, revision=0),
        _stmt(ik, date(2023, 12, 31), "revenue", 650.0, q=4, revision=1),
        _stmt(ik, date(2024, 3, 31), "revenue", 120.0, q=1),
    ]
    announces = [
        _ann(ik, date(2023, 3, 31), datetime(2023, 4, 28, 15, 0, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 6, 30), datetime(2023, 8, 28, 15, 0, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 9, 30), datetime(2023, 10, 28, 15, 0, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 12, 31), datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc), revision=0),
        _ann(ik, date(2023, 12, 31), datetime(2024, 4, 15, 10, 0, tzinfo=timezone.utc), revision=1),
        _ann(ik, date(2024, 3, 31), datetime(2024, 4, 28, 15, 0, tzinfo=timezone.utc)),
    ]

    wide = pivot_statements(pd.DataFrame([s.__dict__ for s in statements]))
    joined = attach_announce(wide, pd.DataFrame([a.__dict__ for a in announces]))
    sq = to_single_quarter(joined)

    rev0_fy = sq[(sq["report_period_end"] == date(2023, 12, 31)) & (sq["revision"] == 0)].iloc[0]
    rev1_fy = sq[(sq["report_period_end"] == date(2023, 12, 31)) & (sq["revision"] == 1)].iloc[0]
    assert rev0_fy["revenue__sq"] == pytest.approx(150.0)
    assert rev1_fy["revenue__sq"] == pytest.approx(250.0)

    metrics = compute_period_metrics(joined)
    ttm_q1 = [
        r
        for r in metrics
        if r["metric_code"] == "revenue_ttm"
        and r["report_period_end"] == date(2024, 3, 31)
    ]
    assert ttm_q1 and ttm_q1[0]["value"] == pytest.approx(670.0)


def test_missing_prior_quarter_sq_and_ttm_none(sample_universe: str):
    ik = sample_universe
    statements = [
        _stmt(ik, date(2023, 3, 31), "revenue", 100.0, q=1),
        _stmt(ik, date(2023, 9, 30), "revenue", 400.0, q=3),  # no Q2
    ]
    announces = [
        _ann(ik, date(2023, 3, 31), datetime(2023, 4, 28, 15, 0, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 9, 30), datetime(2023, 10, 28, 15, 0, tzinfo=timezone.utc)),
    ]
    wide = pivot_statements(pd.DataFrame([s.__dict__ for s in statements]))
    joined = attach_announce(wide, pd.DataFrame([a.__dict__ for a in announces]))
    sq = to_single_quarter(joined)
    q3 = sq[sq["report_period_end"] == date(2023, 9, 30)].iloc[0]
    assert pd.isna(q3["revenue__sq"]) or q3["revenue__sq"] is None

    metrics = compute_period_metrics(joined)
    ttm_q3 = [
        r
        for r in metrics
        if r["metric_code"] == "revenue_ttm" and r["report_period_end"] == date(2023, 9, 30)
    ]
    assert ttm_q3 == []


def _quarterly_history(
    ik: str,
    sq_by_quarter: dict[tuple[int, int], float],
    *,
    field: str = "revenue",
    statement_type: str = "income",
) -> tuple[list[StatementFieldRow], list[AnnounceRow]]:
    """Build YTD cumulative statements + announces from single-quarter values."""
    statements: list[StatementFieldRow] = []
    announces: list[AnnounceRow] = []
    ytd: dict[int, float] = {}
    for (fy, q), sq in sorted(sq_by_quarter.items()):
        pe = _quarter_end(fy, q)
        ytd[fy] = (ytd.get(fy, 0.0) if q > 1 else 0.0) + sq
        statements.append(_stmt(ik, pe, field, ytd[fy], statement_type=statement_type, q=q))
        announces.append(_ann(ik, pe, _disclosed(pe)))
    return statements, announces


def _quarter_end(fy: int, q: int) -> date:
    return {1: date(fy, 3, 31), 2: date(fy, 6, 30), 3: date(fy, 9, 30), 4: date(fy, 12, 31)}[q]


def _disclosed(pe: date) -> datetime:
    if pe.month == 12:
        return datetime(pe.year + 1, 3, 28, 15, 0, tzinfo=timezone.utc)
    return datetime(pe.year, pe.month + 1, 25, 15, 0, tzinfo=timezone.utc)


def _metric(rows: list[dict], code: str, pe: date, revision: int | None = None) -> list[dict]:
    return [
        r
        for r in rows
        if r["metric_code"] == code
        and r["report_period_end"] == pe
        and (revision is None or r["revision"] == revision)
    ]


def test_accruals_uses_ttm(sample_universe: str):
    ik = sample_universe
    np_sq = {(2022, 4): 10.0, (2023, 1): 10.0, (2023, 2): 10.0, (2023, 3): 10.0}
    ocf_sq = {(2022, 4): 7.0, (2023, 1): 7.0, (2023, 2): 7.0, (2023, 3): 7.0}
    # 2022 Q1–Q3 needed so 2022 Q4 single quarter can be differenced.
    for q in (1, 2, 3):
        np_sq[(2022, q)] = 10.0
        ocf_sq[(2022, q)] = 7.0
    s1, announces = _quarterly_history(ik, np_sq, field="net_profit_parent")
    s2, _ = _quarterly_history(ik, ocf_sq, field="cash_from_operations", statement_type="cashflow")
    pe = date(2023, 9, 30)
    s3 = [_stmt(ik, pe, "total_assets", 400.0, statement_type="balance", q=3)]
    metrics = statements_to_pit_metrics(
        pd.DataFrame([s.__dict__ for s in s1 + s2 + s3]),
        pd.DataFrame([a.__dict__ for a in announces]),
    )
    accruals = _metric(metrics, "accruals_ratio", pe)
    assert accruals and accruals[0]["value"] == pytest.approx((40.0 - 28.0) / 400.0)


def test_date_only_announce_visible_next_day(sample_universe: str):
    from app.services.research_data.fund_cn.adapters.announce import as_utc
    from app.services.research_data.fund_cn.compute import forward_fill_report_factors

    ik = sample_universe
    day = date(2024, 3, 28)
    at = as_utc(day)
    assert at == datetime(2024, 3, 28, 16, 0, tzinfo=timezone.utc)
    assert as_utc(datetime(2024, 3, 28)) == at  # naive midnight == date-only
    rows = [
        {
            "instrument_key": ik,
            "metric_code": "roe",
            "report_period_end": date(2023, 12, 31),
            "available_time": at,
            "revision": 0,
            "value": 0.1,
        }
    ]
    panel = forward_fill_report_factors(
        rows, [day, date(2024, 3, 29)], [ik], factor_ids_subset=["roe"]
    )
    by_day = dict(zip(panel["trading_date"], panel["roe"]))
    assert by_day["2024-03-28"] is None or pd.isna(by_day["2024-03-28"])
    assert by_day["2024-03-29"] == pytest.approx(0.1)


def _pit_row(ik: str, metric: str, pe: date, at: datetime, value: float, revision: int = 0) -> dict:
    return {
        "instrument_key": ik,
        "metric_code": metric,
        "report_period_start": None,
        "report_period_end": pe,
        "fiscal_year": pe.year,
        "fiscal_quarter": (pe.month - 1) // 3 + 1,
        "publish_time": at,
        "available_time": at,
        "value": value,
        "unit": "ratio",
        "currency": "CNY",
        "revision": revision,
        "is_restatement": revision > 0,
        "source": "test",
        "source_record_id": f"{ik}:{metric}:{pe}:r{revision}",
        "data_version": "test.v1",
    }


def test_late_old_period_restatement_does_not_roll_back(tmp_path: Path, sample_universe: str):
    from app.services.research_data.fund_cn.compute import forward_fill_report_factors
    from app.services.research_data.ingest.fundamental_pit import ingest_pit_fundamental

    ik = sample_universe
    rows = [
        _pit_row(ik, "roe", date(2023, 12, 31), datetime(2024, 3, 28, 15, tzinfo=timezone.utc), 0.10),
        _pit_row(ik, "roe", date(2024, 3, 31), datetime(2024, 4, 26, 15, tzinfo=timezone.utc), 0.11),
        # FY2023 restated in June — must not replace visible 2024Q1.
        _pit_row(ik, "roe", date(2023, 12, 31), datetime(2024, 6, 10, 15, tzinfo=timezone.utc), 0.20, 1),
    ]
    panel = forward_fill_report_factors(
        rows, [date(2024, 4, 1), date(2024, 6, 12)], [ik], factor_ids_subset=["roe"]
    )
    by_day = dict(zip(panel["trading_date"], panel["roe"]))
    assert by_day["2024-04-01"] == pytest.approx(0.10)
    assert by_day["2024-06-12"] == pytest.approx(0.11)

    store = LocalCanonicalStore(tmp_path / "canonical")
    registry = LocalJsonRegistry(tmp_path / "registry")
    ingest_pit_fundamental(
        store, instrument_keys=[ik], version="test.v1", registry=registry, rows=rows,
        allow_synthetic=False,
    )
    query = DataQuery(store, registry)
    got = query.fundamental([ik], ["roe"], datetime(2024, 6, 12, tzinfo=timezone.utc), exchange="CN")
    assert float(got.iloc[0]["value"]) == pytest.approx(0.11)
    assert pd.Timestamp(got.iloc[0]["report_period_end"]).date() == date(2024, 3, 31)


def test_fundamental_query_discovers_older_partitions(tmp_path: Path, sample_universe: str):
    """多年无新披露时，点查仍应找到 KT 之前最后一条历史 PIT 数据。"""
    from app.services.research_data.ingest.fundamental_pit import ingest_pit_fundamental

    ik = sample_universe
    row = _pit_row(
        ik,
        "roe",
        date(2020, 12, 31),
        datetime(2021, 3, 28, 15, tzinfo=timezone.utc),
        0.1,
    )
    store = LocalCanonicalStore(tmp_path / "canonical")
    registry = LocalJsonRegistry(tmp_path / "registry")
    ingest_pit_fundamental(
        store,
        instrument_keys=[ik],
        version="test.v1",
        registry=registry,
        rows=[row],
        allow_synthetic=False,
    )
    got = DataQuery(store, registry).fundamental(
        [ik],
        ["roe"],
        datetime(2025, 1, 2, tzinfo=timezone.utc),
        exchange="CN",
    )
    assert len(got) == 1
    assert float(got.iloc[0]["value"]) == pytest.approx(0.1)


def test_report_forward_fill_staleness_cap(sample_universe: str):
    from app.services.research_data.fund_cn.compute import forward_fill_report_factors

    ik = sample_universe
    rows = [_pit_row(ik, "roe", date(2020, 12, 31), datetime(2021, 3, 28, tzinfo=timezone.utc), 0.1)]
    panel = forward_fill_report_factors(
        rows, [date(2021, 6, 1), date(2024, 1, 2)], [ik], factor_ids_subset=["roe"]
    )
    by_day = dict(zip(panel["trading_date"], panel["roe"]))
    assert by_day["2021-06-01"] == pytest.approx(0.1)
    assert by_day["2024-01-02"] is None or pd.isna(by_day["2024-01-02"])


def test_ttm_none_when_history_has_gap(sample_universe: str):
    ik = sample_universe
    sq = {(2022, q): 10.0 for q in (1, 2, 3, 4)}
    sq[(2023, 1)] = 10.0
    sq[(2023, 3)] = 30.0  # 2023 Q2 missing; YTD Q3 alone
    statements, announces = _quarterly_history(ik, sq)
    # _quarterly_history accumulates YTD; with Q2 missing the Q3 cum is 40 (10 + 30).
    metrics = statements_to_pit_metrics(
        pd.DataFrame([s.__dict__ for s in statements]),
        pd.DataFrame([a.__dict__ for a in announces]),
    )
    assert _metric(metrics, "revenue_ttm", date(2023, 3, 31))
    assert _metric(metrics, "revenue_ttm", date(2023, 9, 30)) == []
    assert _metric(metrics, "revenue_yoy", date(2023, 9, 30)) == []


def test_ttm_rediffs_after_late_q3_restatement(sample_universe: str):
    """Q3 restated after Q4 is out: later TTM uses the new Q3 for both Q3 and Q4 single quarters."""
    ik = sample_universe
    statements = [
        _stmt(ik, date(2023, 3, 31), "revenue", 100.0, q=1),
        _stmt(ik, date(2023, 6, 30), "revenue", 200.0, q=2),
        _stmt(ik, date(2023, 9, 30), "revenue", 300.0, q=3, revision=0),
        _stmt(ik, date(2023, 12, 31), "revenue", 500.0, q=4),
        _stmt(ik, date(2023, 9, 30), "revenue", 350.0, q=3, revision=1),
        _stmt(ik, date(2024, 3, 31), "revenue", 150.0, q=1),
    ]
    announces = [
        _ann(ik, date(2023, 3, 31), datetime(2023, 4, 25, 15, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 6, 30), datetime(2023, 8, 25, 15, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 9, 30), datetime(2023, 10, 25, 15, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 12, 31), datetime(2024, 3, 28, 15, tzinfo=timezone.utc)),
        _ann(ik, date(2023, 9, 30), datetime(2024, 4, 2, 15, tzinfo=timezone.utc), revision=1),
        _ann(ik, date(2024, 3, 31), datetime(2024, 4, 26, 15, tzinfo=timezone.utc)),
    ]
    metrics = statements_to_pit_metrics(
        pd.DataFrame([s.__dict__ for s in statements]),
        pd.DataFrame([a.__dict__ for a in announces]),
    )
    # sq: Q2=100, Q3=350-200=150, Q4=500-350=150, 2024Q1=150 → 550 (frozen sq would give 600).
    ttm = _metric(metrics, "revenue_ttm", date(2024, 3, 31))
    assert ttm and ttm[0]["value"] == pytest.approx(550.0)


def test_alias_priority_and_derived_gross_margin(sample_universe: str):
    from app.services.research_data.fund_cn.adapters.akshare_adapter import (
        AkshareStatementAdapter,
        em_symbol,
    )

    assert em_symbol("600519") == "SH600519"
    assert em_symbol("000001") == "SZ000001"
    assert em_symbol("830799") == "BJ830799"

    income = pd.DataFrame(
        [
            {
                "REPORT_DATE": "2023-12-31 00:00:00",
                "NOTICE_DATE": "2024-03-28 00:00:00",
                "OPERATE_INCOME": 90.0,
                "TOTAL_OPERATE_INCOME": 100.0,
                "OPERATE_COST": 30.0,
                "PARENT_NETPROFIT": 18.0,
                "NETPROFIT": 20.0,
                "SALE_EXPENSE": 5.0,
                "MANAGE_EXPENSE": 4.0,
                "RESEARCH_EXPENSE": 0.0,
                "FINANCE_EXPENSE": 0.0,
            }
        ]
    )
    balance = pd.DataFrame(
        [
            {
                "REPORT_DATE": "2023-12-31 00:00:00",
                "NOTICE_DATE": "2024-03-28 00:00:00",
                "TOTAL_ASSETS": 300.0,
                "TOTAL_PARENT_EQUITY": 180.0,
                "TOTAL_EQUITY": 200.0,
                "SHARE_CAPITAL": 10.0,
                # 三项债务均明确出现时才允许派生“有息负债为 0”。
                "SHORT_LOAN": 0.0,
                "LONG_LOAN": 0.0,
                "BOND_PAYABLE": 0.0,
            }
        ]
    )
    adapter = AkshareStatementAdapter(
        income_fetcher=lambda _s: income,
        balance_fetcher=lambda _s: balance,
        cashflow_fetcher=lambda _s: pd.DataFrame(),
    )
    ik = sample_universe
    stmts = adapter.fetch_statements([ik])
    by_field = {s.field_code: s.value for s in stmts}
    assert by_field["revenue"] == 90.0
    assert by_field["net_profit_parent"] == 18.0
    assert by_field["shareholder_equity"] == 180.0
    assert by_field["interest_bearing_debt"] == 0.0  # debt-free balance sheet
    announces = adapter.fetch_announcements([ik])
    assert len(announces) == 1
    assert announces[0].available_time == datetime(2024, 3, 28, 16, 0, tzinfo=timezone.utc)

    metrics = statements_to_pit_metrics(
        pd.DataFrame([s.__dict__ for s in stmts]),
        pd.DataFrame([a.__dict__ for a in announces]),
    )
    pe = date(2023, 12, 31)
    assert _metric(metrics, "gross_margin", pe)[0]["value"] == pytest.approx(60.0 / 90.0)
    assert _metric(metrics, "expense_ratio", pe)[0]["value"] == pytest.approx(9.0 / 90.0)
    assert _metric(metrics, "roe", pe)[0]["value"] == pytest.approx(18.0 / 180.0)

    summary = coverage_summary(
        pd.DataFrame([s.__dict__ for s in stmts]),
        pd.DataFrame([a.__dict__ for a in announces]),
        factors=[f for f in FACTOR_DEFINITIONS if f.factor_id == "gross_margin"],
    )
    assert summary["factors"][0]["RAW_OK"] == "ok"


def test_eastmoney_update_date_is_conservative_visibility(sample_universe: str):
    """最新修订值只能从 UPDATE_DATE 可见，不能回填至原 NOTICE_DATE。"""
    from app.services.research_data.fund_cn.adapters.akshare_adapter import AkshareStatementAdapter

    income = pd.DataFrame(
        [
            {
                "REPORT_DATE": "2023-12-31",
                "NOTICE_DATE": "2024-03-28",
                "UPDATE_DATE": "2024-04-15",
                "OPERATE_INCOME": 120.0,
                "PARENT_NETPROFIT": 20.0,
            }
        ]
    )
    balance = pd.DataFrame(
        [
            {
                "REPORT_DATE": "2023-12-31",
                "NOTICE_DATE": "2024-03-29",
                "UPDATE_DATE": "2024-03-29",
                "TOTAL_ASSETS": 300.0,
                "TOTAL_PARENT_EQUITY": 180.0,
            }
        ]
    )
    adapter = AkshareStatementAdapter(
        income_fetcher=lambda _s: income,
        balance_fetcher=lambda _s: balance,
        cashflow_fetcher=lambda _s: pd.DataFrame(),
    )
    statements = adapter.fetch_statements([sample_universe])
    announcements = adapter.fetch_announcements([sample_universe])
    assert statements and {row.revision for row in statements} == {1}
    assert len(announcements) == 1
    assert announcements[0].revision == 1
    assert announcements[0].is_restatement
    assert announcements[0].available_time == datetime(
        2024, 4, 15, 16, 0, tzinfo=timezone.utc
    )


def test_partial_debt_and_expenses_do_not_create_understated_derived_values(
    sample_universe: str,
):
    """组成项不完整时保持缺失，避免把部分和误当成完整财务指标。"""
    from app.services.research_data.fund_cn.adapters.akshare_adapter import (
        dataframe_to_statement_rows,
        merge_interest_bearing,
    )

    balance = pd.DataFrame(
        [{"REPORT_DATE": "2023-12-31", "TOTAL_ASSETS": 100.0, "SHORT_LOAN": 10.0}]
    )
    debt_rows = merge_interest_bearing(
        dataframe_to_statement_rows(
            balance,
            instrument_key=sample_universe,
            statement_type="balance",
            source="test",
        )
    )
    assert not any(row.field_code == "interest_bearing_debt" for row in debt_rows)

    partial = derive_fields(pd.DataFrame([{"revenue": 100.0, "selling_expense": 5.0}]))
    assert "operating_expenses" not in partial or pd.isna(partial.iloc[0]["operating_expenses"])


def test_derived_fcf_normalizes_capex_sign_and_rejects_non_finite_values(
    sample_universe: str,
):
    """资本开支正负记账应得到同一 FCF，非有限输入不得进入 PIT 指标。"""
    derived = derive_fields(
        pd.DataFrame(
            [
                {"cash_from_operations": 100.0, "capex": 30.0},
                {"cash_from_operations": 100.0, "capex": -30.0},
            ]
        )
    )
    assert list(derived["free_cash_flow"]) == pytest.approx([70.0, 70.0])

    pe = date(2023, 12, 31)
    rows = statements_to_pit_metrics(
        pd.DataFrame(
            [
                _stmt(sample_universe, pe, "net_profit_parent", float("inf")).__dict__,
                _stmt(
                    sample_universe,
                    pe,
                    "shareholder_equity",
                    100.0,
                    statement_type="balance",
                ).__dict__,
            ]
        ),
        pd.DataFrame(
            [
                _ann(
                    sample_universe,
                    pe,
                    datetime(2024, 3, 28, 15, tzinfo=timezone.utc),
                ).__dict__
            ]
        ),
    )
    assert not [row for row in rows if row["metric_code"] in {"net_profit_parent", "roe"}]

    from app.services.research_data.fund_cn.compute import compute_valuation_factors

    at = datetime(2024, 3, 28, 15, tzinfo=timezone.utc)
    valuation = compute_valuation_factors(
        [
            _pit_row(sample_universe, "net_income_ttm", pe, at, 1e-15),
            _pit_row(sample_universe, "shares_outstanding", pe, at, 10.0),
        ],
        pd.DataFrame(
            [
                {
                    "instrument_key": sample_universe,
                    "trading_date": date(2024, 4, 1),
                    "close": 10.0,
                }
            ]
        ),
        factor_ids_subset=["pe_ttm"],
    )
    assert valuation.iloc[0]["pe_ttm"] is None


def test_ttm_roe_comparable_between_q1_and_fy_reporters():
    a, b = "CNStock:000001", "CNStock:000002"
    # A: only FY2023 visible (np 100, equity 1000). B: quarterly through 2024Q1, 25 per quarter.
    sa = [
        _stmt(a, date(2023, 12, 31), "net_profit_parent", 100.0, q=4),
        _stmt(a, date(2023, 12, 31), "shareholder_equity", 1000.0, statement_type="balance", q=4),
    ]
    ann = [_ann(a, date(2023, 12, 31), datetime(2024, 3, 28, 15, tzinfo=timezone.utc))]
    sq = {(2023, q): 25.0 for q in (1, 2, 3, 4)}
    sq[(2024, 1)] = 25.0
    sb, ann_b = _quarterly_history(b, sq, field="net_profit_parent")
    sb.append(_stmt(b, date(2024, 3, 31), "shareholder_equity", 1000.0, statement_type="balance", q=1))
    metrics = statements_to_pit_metrics(
        pd.DataFrame([s.__dict__ for s in sa + sb]),
        pd.DataFrame([x.__dict__ for x in ann + ann_b]),
    )
    roe_a = [r for r in metrics if r["metric_code"] == "roe" and r["instrument_key"] == a]
    roe_b = _metric(metrics, "roe", date(2024, 3, 31))
    assert roe_a[0]["value"] == pytest.approx(0.1)
    assert roe_b[0]["value"] == pytest.approx(0.1)  # YTD would give 0.025


def test_daily_share_capital_keeps_pe_continuous_through_bonus_issue(sample_universe: str):
    from app.services.research_data.fund_cn.adapters.base import ShareCapitalRow
    from app.services.research_data.fund_cn.compute import compute_valuation_factors

    ik = sample_universe
    at = datetime(2024, 3, 28, 15, tzinfo=timezone.utc)
    pit_rows = [
        _pit_row(ik, "net_income_ttm", date(2023, 12, 31), at, 1e9),
        _pit_row(ik, "shares_outstanding", date(2023, 12, 31), at, 1e9),
    ]
    # 10送10: announced 2024-04-20, ex-date 2024-05-10; raw close halves.
    shares = pd.DataFrame(
        [
            ShareCapitalRow(ik, date(2023, 12, 31), datetime(2024, 3, 28, 16, tzinfo=timezone.utc), 1e9).__dict__,
            ShareCapitalRow(ik, date(2024, 5, 10), datetime(2024, 4, 20, 16, tzinfo=timezone.utc), 2e9).__dict__,
        ]
    )
    market = pd.DataFrame(
        [
            {"instrument_key": ik, "trading_date": date(2024, 5, 9), "close": 20.0},
            {"instrument_key": ik, "trading_date": date(2024, 5, 10), "close": 10.0},
        ]
    )
    panel = compute_valuation_factors(
        pit_rows, market, factor_ids_subset=["pe_ttm"], share_capital=shares
    )
    assert list(panel["pe_ttm"]) == pytest.approx([20.0, 20.0])

    stale = compute_valuation_factors(pit_rows, market, factor_ids_subset=["pe_ttm"])
    assert list(stale["pe_ttm"]) == pytest.approx([20.0, 10.0])  # report shares lag the split


def test_compute_period_metrics_perf_smoke():
    import time

    rng_rows: list[StatementFieldRow] = []
    announces: list[AnnounceRow] = []
    fields = (
        ("revenue", "income"),
        ("net_profit_parent", "income"),
        ("cash_from_operations", "cashflow"),
        ("total_assets", "balance"),
        ("shareholder_equity", "balance"),
    )
    for i in range(500):
        ik = f"CNStock:{i:06d}"
        for fy in range(2015, 2025):
            for q in (1, 2, 3, 4):
                pe = _quarter_end(fy, q)
                for field, stype in fields:
                    value = 100.0 * q if stype != "balance" else 1000.0
                    rng_rows.append(_stmt(ik, pe, field, value, statement_type=stype, q=q))
                announces.append(_ann(ik, pe, _disclosed(pe)))
    statements = pd.DataFrame([s.__dict__ for s in rng_rows])
    ann = pd.DataFrame([a.__dict__ for a in announces])
    started = time.perf_counter()
    metrics = statements_to_pit_metrics(statements, ann)
    elapsed = time.perf_counter() - started
    assert metrics
    assert elapsed < 60.0, f"500 instruments x 40 periods took {elapsed:.1f}s"


def test_coverage_nan_values_fail_raw(sample_universe: str):
    ik = sample_universe
    pe = date(2023, 12, 31)
    statements = pd.DataFrame(
        [
            {
                "instrument_key": ik,
                "report_period_end": pe,
                "fiscal_year": 2023,
                "fiscal_quarter": 4,
                "statement_type": "income",
                "field_code": "revenue",
                "value": float("nan"),
                "source": "test",
                "source_record_id": "x",
                "revision": 0,
            }
        ]
    )
    announce = pd.DataFrame(
        [
            {
                "instrument_key": ik,
                "report_period_end": pe,
                "publish_time": datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc),
                "available_time": datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc),
                "revision": 0,
                "is_restatement": False,
                "source": "test",
                "source_record_id": "a",
            }
        ]
    )
    report = evaluate_metric_coverage(statements, announce, "revenue")
    assert report.value_missing_rate == pytest.approx(1.0)
    assert report.raw_ok is False


def test_coverage_mvp_eligible_with_complete_fields(sample_universe: str):
    ik = sample_universe
    pe = date(2023, 12, 31)
    fields = [
        ("revenue", 100.0, "income"),
        ("net_profit_parent", 10.0, "income"),
        ("gross_profit", 40.0, "income"),
        ("shareholder_equity", 100.0, "balance"),
        ("total_assets", 200.0, "balance"),
        ("total_liabilities", 100.0, "balance"),
        ("cash_from_operations", 12.0, "cashflow"),
        ("shares_outstanding", 10.0, "balance"),
    ]
    statements = [
        _stmt(ik, pe, code, val, statement_type=stype) for code, val, stype in fields
    ]
    announces = [_ann(ik, pe, datetime(2024, 3, 28, 15, 0, tzinfo=timezone.utc))]
    summary = coverage_summary(
        pd.DataFrame([s.__dict__ for s in statements]),
        pd.DataFrame([a.__dict__ for a in announces]),
    )
    assert summary["eligible_count"] > 0
    assert "roe" in summary["eligible_factor_ids"]


def test_announce_keeps_earliest_available_time(sample_universe: str):
    ik = sample_universe
    pe = date(2023, 12, 31)
    early = datetime(2024, 3, 28, 10, 0, tzinfo=timezone.utc)
    late = datetime(2024, 3, 28, 18, 0, tzinfo=timezone.utc)
    statements = [
        _stmt(ik, pe, "revenue", 100.0),
        _stmt(ik, pe, "net_profit_parent", 10.0),
        _stmt(ik, pe, "shareholder_equity", 100.0, statement_type="balance"),
    ]
    announces = [
        AnnounceRow(
            instrument_key=ik,
            report_period_end=pe,
            publish_time=late,
            available_time=late,
            revision=0,
            is_restatement=False,
            source="test",
            source_record_id="late",
        ),
        AnnounceRow(
            instrument_key=ik,
            report_period_end=pe,
            publish_time=early,
            available_time=early,
            revision=0,
            is_restatement=False,
            source="test",
            source_record_id="early",
        ),
    ]
    wide = pivot_statements(pd.DataFrame([s.__dict__ for s in statements]))
    joined = attach_announce(wide, pd.DataFrame([a.__dict__ for a in announces]))
    assert len(joined) == 1
    assert pd.Timestamp(joined.iloc[0]["available_time"]) == pd.Timestamp(early)
    assert joined.iloc[0]["announce_record_id"] == "early"
