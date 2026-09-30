"""is_equity / is_fund / is_default_symbol 边界测试。"""
from __future__ import annotations

import pytest

from app.services.level2_ingest.symbols import is_default_symbol, is_equity, is_fund

_A_SHARES = [
    ("000001.SZ", "深市主板"),
    ("002049.SZ", "中小板"),
    ("300001.SZ", "创业板"),
    ("600460.SH", "沪市主板"),
    ("688001.SH", "科创板"),
]

_FUNDS = [
    ("159838.SZ", "深市ETF"),
    ("160105.SZ", "深市LOF"),
    ("501000.SH", "沪市基金"),
    ("510300.SH", "沪市ETF"),
    ("511880.SH", "货币ETF"),
    ("588000.SH", "科创板ETF"),
]

_EXCLUDED = [
    ("123138.SZ", "可转债"),
    ("110075.SH", "可转债"),
    ("900901.SH", "沪B"),
    ("200002.SZ", "深B"),
]


@pytest.mark.parametrize("code,_label", _A_SHARES)
def test_is_equity_a_share(code: str, _label: str) -> None:
    assert is_equity(code) is True
    assert is_fund(code) is False
    assert is_default_symbol(code) is True


@pytest.mark.parametrize("code,_label", _FUNDS)
def test_is_fund_and_default(code: str, _label: str) -> None:
    """场内基金：非 A 股，但默认标的应保留。"""
    assert is_equity(code) is False
    assert is_fund(code) is True
    assert is_default_symbol(code) is True


@pytest.mark.parametrize("code,_label", _EXCLUDED)
def test_excluded_not_default(code: str, _label: str) -> None:
    """可转债/B 股：既非 A 股也非基金，默认过滤。"""
    assert is_equity(code) is False
    assert is_fund(code) is False
    assert is_default_symbol(code) is False
