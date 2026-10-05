"""dataset_hash 稳定性与 price_policy 敏感性。"""

from __future__ import annotations

from app.services.research_data.hashing import compute_dataset_hash


def _base(**overrides):
    payload = {
        "dataset_definition": {"code": "CSI300_DAILY", "features": ["close"]},
        "dataset_version": "1.0.0",
        "snapshot_id": "snap_1",
        "schema_version": "market_bar_daily@1",
        "processor_version": "proc@1",
        "materializer_version": "none",
        "price_policy": {"adjustment": "none", "return_type": "price"},
    }
    payload.update(overrides)
    return compute_dataset_hash(**payload)


def test_dataset_hash_stable_for_same_inputs():
    assert _base() == _base()


def test_price_policy_changes_hash():
    h1 = _base(price_policy={"adjustment": "none", "return_type": "price"})
    h2 = _base(price_policy={"adjustment": "post", "return_type": "price"})
    assert h1 != h2


def test_snapshot_id_changes_hash():
    assert _base(snapshot_id="snap_1") != _base(snapshot_id="snap_2")


def test_case_d_processor_version_changes_hash():
    """Case D：processor_version 变化必须改变 dataset_hash。"""
    assert _base(processor_version="proc@1") != _base(processor_version="proc@2")


def test_case_e_schema_version_changes_hash():
    """Case E：schema_version 变化必须改变 dataset_hash。"""
    assert _base(schema_version="market_bar_daily@1") != _base(
        schema_version="market_bar_daily@2"
    )
