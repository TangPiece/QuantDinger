"""Phase 2B：LabelAdapter + Feature/Label 路径隔离与泄漏语义。"""

from __future__ import annotations

import pytest

from app.services.research_data.contracts import LabelDefinition
from app.services.research_data.qlib_adapter import (
    FeatureAdapter,
    LabelAdapter,
    UnsupportedFeatureError,
    default_fwd_ret_label,
)


def test_label_fwd_ret_compile():
    la = LabelAdapter()
    label, compiled = la.resolve(None)
    assert label.code == "fwd_ret"
    assert compiled.horizon == 5
    assert compiled.qlib_expression == "Ref($close, -5) / $close - 1"


def test_label_negative_ref_only():
    la = LabelAdapter()
    lab = LabelDefinition(
        code="fwd_close",
        version="1",
        name="fwd",
        expression="Ref($close, -3)",
        horizon=3,
    )
    compiled = la.compile(lab)
    assert compiled.horizon == 3
    assert compiled.qlib_expression == "Ref($close, -3)"


def test_feature_rejects_negative_ref_and_return():
    """Feature 路径禁止负向 Ref / 收益式，防止把 Label 泄漏进 Feature。"""
    fa = FeatureAdapter()
    with pytest.raises(UnsupportedFeatureError):
        fa.compile_one("Ref($close, -5)")
    with pytest.raises(UnsupportedFeatureError):
        fa.compile_one("Ref($close, -5) / $close - 1")


def test_label_rejects_positive_ref():
    la = LabelAdapter()
    with pytest.raises(UnsupportedFeatureError):
        la.compile(
            LabelDefinition(
                code="bad",
                version="1",
                name="bad",
                expression="Ref($close, 5)",
            )
        )


def test_default_fwd_ret_helper():
    lab = default_fwd_ret_label(horizon=5)
    assert "Ref($close, -5)" in lab.expression
