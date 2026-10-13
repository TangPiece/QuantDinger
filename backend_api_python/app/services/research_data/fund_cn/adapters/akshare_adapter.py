"""AKShare statement adapter — raw fetch only; never call from factor compute.

Eastmoney ``stock_*_sheet_by_report_em`` returns **English** column names
(verified against akshare 1.19: ``OPERATE_INCOME``, ``PARENT_NETPROFIT``,
``TOTAL_PARENT_EQUITY``, ``NETCASH_OPERATE`` …) plus ``NOTICE_DATE`` /
``UPDATE_DATE``. Chinese names are kept as secondary candidates for other dumps.

PIT limitation: em only serves the latest version of each period. When a period
was restated (``UPDATE_DATE`` > ``NOTICE_DATE``) the restated numbers carry the
original disclosure date — a residual look-ahead risk documented in README.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable, Sequence

import pandas as pd

from .announce import as_utc
from .base import (
    AnnounceRow,
    StatementAdapter,
    StatementFieldRow,
    a_code_to_instrument,
    instrument_to_a_code,
)

_log = logging.getLogger(__name__)

# statement_type → field_code → source columns in priority order (first non-null wins).
_FIELD_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    "income": {
        "revenue": ("OPERATE_INCOME", "营业收入", "TOTAL_OPERATE_INCOME", "营业总收入", "一、营业总收入"),
        "net_profit_parent": ("PARENT_NETPROFIT", "归属于母公司所有者的净利润", "归母净利润"),
        "net_profit_deducted": (
            "DEDUCT_PARENT_NETPROFIT",
            "扣除非经常性损益后的净利润",
            "扣非净利润",
        ),
        "operating_profit": ("OPERATE_PROFIT", "营业利润", "三、营业利润"),
        "gross_profit": ("毛利",),
        "operating_cost": ("OPERATE_COST", "营业成本"),
        "selling_expense": ("SALE_EXPENSE", "销售费用"),
        "admin_expense": ("MANAGE_EXPENSE", "管理费用"),
        "rd_expense": ("RESEARCH_EXPENSE", "研发费用"),
        "financial_expense": ("FINANCE_EXPENSE", "财务费用"),
    },
    "balance": {
        "total_assets": ("TOTAL_ASSETS", "资产总计", "总资产"),
        "total_liabilities": ("TOTAL_LIABILITIES", "负债合计", "总负债"),
        "shareholder_equity": (
            "TOTAL_PARENT_EQUITY",
            "归属于母公司股东权益合计",
            "归属于母公司所有者权益合计",
        ),
        "current_assets": ("TOTAL_CURRENT_ASSETS", "流动资产合计"),
        "current_liabilities": ("TOTAL_CURRENT_LIAB", "流动负债合计"),
        "accounts_receivable": ("ACCOUNTS_RECE", "应收账款"),
        "inventory": ("INVENTORY", "存货"),
        "short_term_debt": ("SHORT_LOAN", "短期借款"),
        "long_term_debt": ("LONG_LOAN", "长期借款"),
        "bonds_payable": ("BOND_PAYABLE", "应付债券"),
        "shares_outstanding": ("SHARE_CAPITAL", "实收资本(或股本)", "股本"),
    },
    "cashflow": {
        "cash_from_operations": ("NETCASH_OPERATE", "经营活动产生的现金流量净额"),
        "capex": ("CONSTRUCT_LONG_ASSET", "购建固定资产、无形资产和其他长期资产支付的现金"),
    },
}

_PERIOD_COLS: tuple[str, ...] = ("REPORT_DATE", "报告日", "报告期", "REPORT_DATE_NAME", "日期")
_NOTICE_COLS: tuple[str, ...] = ("NOTICE_DATE", "公告日期", "披露日期")

Fetcher = Callable[[str], pd.DataFrame | None]


def _parse_period(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        parsed = pd.to_datetime(value)
    except Exception:
        return None
    return None if pd.isna(parsed) else parsed.date()


def _fiscal_quarter(period_end: date) -> int:
    return (period_end.month - 1) // 3 + 1


def _float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(out) else out


def em_symbol(code: str) -> str:
    """600519 → SH600519; 000001 → SZ000001; 8xxxxx/4xxxxx/920xxx → BJ."""
    code = str(code).zfill(6)
    if code.startswith(("6", "9")) and not code.startswith("92"):
        return f"SH{code}"
    if code.startswith(("4", "8", "92")):
        return f"BJ{code}"
    return f"SZ{code}"


def _first_col(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    return next((c for c in candidates if c in frame.columns), None)


def dataframe_to_statement_rows(
    frame: pd.DataFrame,
    *,
    instrument_key: str,
    statement_type: str,
    source: str,
    period_col_candidates: Sequence[str] = _PERIOD_COLS,
) -> list[StatementFieldRow]:
    """Map one statement sheet to field rows using priority candidates (no last-wins)."""
    if frame is None or frame.empty:
        return []
    period_col = _first_col(frame, period_col_candidates)
    if period_col is None:
        return []
    candidates = _FIELD_CANDIDATES.get(statement_type, {})
    present = {
        field: [c for c in cols if c in frame.columns]
        for field, cols in candidates.items()
    }
    rows: list[StatementFieldRow] = []
    for _, raw in frame.iterrows():
        period_end = _parse_period(raw[period_col])
        if period_end is None:
            continue
        for field, cols in present.items():
            num = None
            for col in cols:
                num = _float(raw[col])
                if num is not None:
                    break
            if num is None:
                continue
            rows.append(
                StatementFieldRow(
                    instrument_key=instrument_key,
                    report_period_end=period_end,
                    report_period_start=None,
                    fiscal_year=period_end.year,
                    fiscal_quarter=_fiscal_quarter(period_end),
                    statement_type=statement_type,
                    field_code=field,
                    value=num,
                    source=source,
                    source_record_id=f"{instrument_key}:{statement_type}:{period_end.isoformat()}:{field}",
                )
            )
    return rows


def dataframe_to_announce_rows(
    frame: pd.DataFrame,
    *,
    instrument_key: str,
    source: str,
) -> list[AnnounceRow]:
    """One AnnounceRow per period from the sheet's NOTICE_DATE (date-only → D+1 visible)."""
    if frame is None or frame.empty:
        return []
    period_col = _first_col(frame, _PERIOD_COLS)
    notice_col = _first_col(frame, _NOTICE_COLS)
    if period_col is None or notice_col is None:
        return []
    out: list[AnnounceRow] = []
    for _, raw in frame.iterrows():
        pe = _parse_period(raw[period_col])
        notice = _parse_period(raw[notice_col])
        if pe is None or notice is None:
            continue
        at = as_utc(notice)
        out.append(
            AnnounceRow(
                instrument_key=instrument_key,
                report_period_end=pe,
                publish_time=at,
                available_time=at,
                revision=0,
                is_restatement=False,
                source=source,
                source_record_id=f"{instrument_key}:{pe.isoformat()}:r0",
            )
        )
    return out


def merge_interest_bearing(rows: list[StatementFieldRow]) -> list[StatementFieldRow]:
    """Derive interest_bearing_debt = short + long + bonds.

    When a balance sheet exists for the period but all debt lines are blank, the
    source convention is "not applicable" → 0 (debt-free issuers). Periods without
    any balance sheet get no interest_bearing_debt row.
    """
    by_key: dict[tuple, dict[str, float]] = {}
    meta: dict[tuple, StatementFieldRow] = {}
    for row in rows:
        if row.statement_type != "balance":
            continue
        key = (row.instrument_key, row.report_period_end, int(getattr(row, "revision", 0) or 0))
        by_key.setdefault(key, {})[row.field_code] = row.value
        meta[key] = row
    extra: list[StatementFieldRow] = []
    for key, fields in by_key.items():
        if "interest_bearing_debt" in fields:
            continue
        components = [
            fields.get("short_term_debt"),
            fields.get("long_term_debt"),
            fields.get("bonds_payable"),
        ]
        present = [c for c in components if c is not None]
        sample = meta[key]
        extra.append(
            StatementFieldRow(
                instrument_key=sample.instrument_key,
                report_period_end=sample.report_period_end,
                report_period_start=sample.report_period_start,
                fiscal_year=sample.fiscal_year,
                fiscal_quarter=sample.fiscal_quarter,
                statement_type="balance",
                field_code="interest_bearing_debt",
                value=float(sum(present)),
                source=sample.source,
                source_record_id=(
                    f"{sample.instrument_key}:balance:{sample.report_period_end.isoformat()}"
                    f":interest_bearing_debt:r{sample.revision}"
                ),
                revision=sample.revision,
            )
        )
    return rows + extra


class AkshareStatementAdapter:
    """Fetch CN statements via injectable AKShare callables (also serves NOTICE_DATE).

    Fetchers receive the Eastmoney symbol (``SH600519``). Sheets are cached per
    instance so ``fetch_announcements`` does not refetch.
    """

    def __init__(
        self,
        *,
        balance_fetcher: Fetcher | None = None,
        income_fetcher: Fetcher | None = None,
        cashflow_fetcher: Fetcher | None = None,
        source: str = "akshare_em",
    ) -> None:
        self._fetchers: dict[str, Fetcher] = {
            "balance": balance_fetcher or self._default_balance,
            "income": income_fetcher or self._default_income,
            "cashflow": cashflow_fetcher or self._default_cashflow,
        }
        self.source = source
        self._cache: dict[tuple[str, str], pd.DataFrame] = {}

    @staticmethod
    def _default_balance(symbol: str) -> pd.DataFrame | None:
        try:
            import akshare as ak  # type: ignore

            return ak.stock_balance_sheet_by_report_em(symbol=symbol)
        except Exception as exc:
            _log.warning("akshare balance failed %s: %s", symbol, exc)
            return None

    @staticmethod
    def _default_income(symbol: str) -> pd.DataFrame | None:
        try:
            import akshare as ak  # type: ignore

            return ak.stock_profit_sheet_by_report_em(symbol=symbol)
        except Exception as exc:
            _log.warning("akshare income failed %s: %s", symbol, exc)
            return None

    @staticmethod
    def _default_cashflow(symbol: str) -> pd.DataFrame | None:
        try:
            import akshare as ak  # type: ignore

            return ak.stock_cash_flow_sheet_by_report_em(symbol=symbol)
        except Exception as exc:
            _log.warning("akshare cashflow failed %s: %s", symbol, exc)
            return None

    def _sheet(self, code: str, statement_type: str) -> pd.DataFrame:
        key = (code, statement_type)
        if key not in self._cache:
            frame = self._fetchers[statement_type](em_symbol(code))
            self._cache[key] = frame if frame is not None else pd.DataFrame()
        return self._cache[key]

    @staticmethod
    def _instrument(key: str, code: str) -> str:
        return key if ":" in key else a_code_to_instrument(code)

    def fetch_statements(
        self,
        instrument_keys: Sequence[str],
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[StatementFieldRow]:
        rows: list[StatementFieldRow] = []
        for key in instrument_keys:
            code = instrument_to_a_code(key)
            instrument = self._instrument(key, code)
            for statement_type in ("balance", "income", "cashflow"):
                rows.extend(
                    dataframe_to_statement_rows(
                        self._sheet(code, statement_type),
                        instrument_key=instrument,
                        statement_type=statement_type,
                        source=self.source,
                    )
                )
        if start is not None:
            rows = [r for r in rows if r.report_period_end >= start]
        if end is not None:
            rows = [r for r in rows if r.report_period_end <= end]
        return merge_interest_bearing(rows)

    def fetch_announcements(
        self,
        instrument_keys: Sequence[str],
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[AnnounceRow]:
        """Earliest NOTICE_DATE per period across the three sheets."""
        best: dict[tuple[str, date], AnnounceRow] = {}
        for key in instrument_keys:
            code = instrument_to_a_code(key)
            instrument = self._instrument(key, code)
            for statement_type in ("income", "balance", "cashflow"):
                for row in dataframe_to_announce_rows(
                    self._sheet(code, statement_type),
                    instrument_key=instrument,
                    source=f"{self.source}_notice",
                ):
                    slot = (row.instrument_key, row.report_period_end)
                    if slot not in best or row.available_time < best[slot].available_time:
                        best[slot] = row
        out = list(best.values())
        if start is not None:
            out = [r for r in out if r.report_period_end >= start]
        if end is not None:
            out = [r for r in out if r.report_period_end <= end]
        return out


# Protocol satisfaction for type checkers
_: StatementAdapter = AkshareStatementAdapter(  # type: ignore[assignment]
    balance_fetcher=lambda _c: pd.DataFrame(),
    income_fetcher=lambda _c: pd.DataFrame(),
    cashflow_fetcher=lambda _c: pd.DataFrame(),
)
