"""Feature 映射：OHLCV OK；未知 expression 拒绝。"""

from __future__ import annotations

import pytest

from app.services.research_data.qlib_materializer.feature_mapper import (
    UnsupportedFeatureError,
    build_feature_mapping,
    resolve_feature_name,
)


def test_basic_features_map():
    assert resolve_feature_name("close") == "close"
    assert resolve_feature_name("$volume") == "volume"
    mapping = build_feature_mapping(["open", "close", "amount"])
    assert mapping["close"]["qlib_feature"] == "$close"
    assert mapping["close"]["source"] == "canonical.market.close"


def test_unsupported_feature_rejected():
    with pytest.raises(UnsupportedFeatureError):
        resolve_feature_name("Ref($close, -1)")
    with pytest.raises(UnsupportedFeatureError):
        build_feature_mapping(["alpha158_roc"])
