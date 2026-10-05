"""Phase 2A：FeatureAdapter 表达式编译。"""

from __future__ import annotations

import pytest

from app.services.research_data.qlib_adapter import FeatureAdapter, UnsupportedFeatureError


def test_compile_atomic_and_window_ops():
    fa = FeatureAdapter()
    assert fa.compile_one("$close").qlib_expression == "$close"
    assert fa.compile_one("close").qlib_expression == "$close"
    assert fa.compile_one("Ref($close, 1)").qlib_expression == "Ref($close, 1)"
    assert fa.compile_one("Mean($close, 5)").qlib_expression == "Mean($close, 5)"
    assert fa.compile_one("Std($high, 10)").qlib_expression == "Std($high, 10)"
    assert fa.compile_one("Max($low, 3)").qlib_expression == "Max($low, 3)"
    assert fa.compile_one("Min($volume, 2)").qlib_expression == "Min($volume, 2)"
    assert fa.compile_one("Slope($close, 5)").qlib_expression == "Slope($close, 5)"


def test_compile_rejects_unknown():
    fa = FeatureAdapter()
    with pytest.raises(UnsupportedFeatureError):
        fa.compile_one("Rank($close)")
    with pytest.raises(UnsupportedFeatureError):
        fa.compile_one("$close / Ref($close, 1) - 1")
    with pytest.raises(UnsupportedFeatureError):
        fa.compile_one("Alpha158")


def test_to_qlib_fields_batch():
    fa = FeatureAdapter()
    fields = fa.to_qlib_fields(["$open", "Mean($close, 5)"])
    assert fields == ["$open", "Mean($close, 5)"]
