"""Phase 2B：QuantDingerQLibHandler / DatasetH / cache / universe / PIT / 一致性。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("qlib")
from qlib.data import D

from app.services.research_data.qlib_adapter import (
    QlibAdapter,
    QuantDingerQLibHandler,
    ResearchDatasetSpec,
    SegmentRange,
    SegmentSpec,
    compute_dataset_artifact_id,
)
from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.validation import compare_feature_values


def _spec(dataset_ref: str, *, force: bool = False) -> ResearchDatasetSpec:
    return ResearchDatasetSpec(
        dataset_ref=dataset_ref,
        segments=SegmentSpec(
            train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
            valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
            test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
        ),
        force_materialize=force,
    )


def test_build_handler_and_dataset_fetch(golden_qlib_env, tmp_path):
    adapter = QlibAdapter(
        golden_qlib_env["query"],
        materializer=golden_qlib_env["materializer"],
        registry=golden_qlib_env["registry"],
        dataset_cache_root=tmp_path / "qlib-dataset-cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    spec = _spec(golden_qlib_env["dataset_ref"])
    qd = adapter.build_qd_handler(spec, force_materialize=True)
    assert isinstance(qd, QuantDingerQLibHandler)
    assert qd.compiled_label.horizon == 5

    feat = qd.fetch(col_set="feature")
    if feat is None or len(feat) == 0:
        feat = qd.fetch()
    assert feat is not None and len(feat) > 0

    label = qd.fetch(col_set="label")
    assert label is not None and len(label) > 0

    ds = adapter.build_dataset(spec)
    assert ds.qd_dataset_hash  # type: ignore[attr-defined]
    assert set(ds.segments.keys()) == {"train", "valid", "test"}
    assert "CNStock:688001" in qd.instruments  # survivor late joiner at end as_of


def test_handler_does_not_call_fundamental(golden_qlib_env, tmp_path):
    query = golden_qlib_env["query"]
    spy = MagicMock(wraps=query.fundamental)
    query.fundamental = spy  # type: ignore[method-assign]
    adapter = QlibAdapter(
        query,
        materializer=golden_qlib_env["materializer"],
        registry=golden_qlib_env["registry"],
        dataset_cache_root=tmp_path / "ds_cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    adapter.build_qd_handler(_spec(golden_qlib_env["dataset_ref"]), force_materialize=True)
    spy.assert_not_called()


def test_universe_matches_snapshot(golden_qlib_env, tmp_path):
    query = golden_qlib_env["query"]
    adapter = QlibAdapter(
        query,
        materializer=golden_qlib_env["materializer"],
        registry=golden_qlib_env["registry"],
        dataset_cache_root=tmp_path / "ds_cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    qd = adapter.build_qd_handler(_spec(golden_qlib_env["dataset_ref"]), force_materialize=True)
    handle = query.dataset(golden_qlib_env["dataset_ref"])
    expected = query.universe(
        handle.definition.universe_code,
        date(2024, 6, 30),
        snapshot_id=handle.definition.snapshot_id,
        universe_version=handle.definition.universe_version,
    )
    assert set(qd.instruments) == set(expected)
    assert "CNStock:999999" not in qd.instruments


def test_dataset_cache_hit_and_segment_change(golden_qlib_env, tmp_path):
    cache_root = tmp_path / "qlib-dataset-cache"
    adapter = QlibAdapter(
        golden_qlib_env["query"],
        materializer=golden_qlib_env["materializer"],
        registry=golden_qlib_env["registry"],
        dataset_cache_root=cache_root,
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    spec = _spec(golden_qlib_env["dataset_ref"])
    ds1 = adapter.build_dataset(spec)
    assert ds1.qd_cache_hit is False  # type: ignore[attr-defined]
    art1 = ds1.qd_artifact_id  # type: ignore[attr-defined]

    ds2 = adapter.build_dataset(spec)
    assert ds2.qd_cache_hit is True  # type: ignore[attr-defined]
    assert ds2.qd_artifact_id == art1  # type: ignore[attr-defined]

    # 改 valid 窗口 → 新 artifact
    spec2 = ResearchDatasetSpec(
        dataset_ref=golden_qlib_env["dataset_ref"],
        segments=SegmentSpec(
            train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
            valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 3, 31)),
            test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
        ),
    )
    ds3 = adapter.build_dataset(spec2)
    assert ds3.qd_artifact_id != art1  # type: ignore[attr-defined]
    assert (cache_root / art1 / "manifest.json").is_file()


def test_close_consistency_via_adapter(golden_qlib_env, tmp_path):
    query = golden_qlib_env["query"]
    adapter = QlibAdapter(
        query,
        materializer=golden_qlib_env["materializer"],
        registry=golden_qlib_env["registry"],
        dataset_cache_root=tmp_path / "ds_cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    qd = adapter.build_qd_handler(_spec(golden_qlib_env["dataset_ref"]), force_materialize=True)
    ik = "CNStock:000001"
    market = query.market(
        [ik],
        date(2024, 1, 1),
        date(2024, 6, 30),
        price_policy=qd.bundle.handle.definition.price_policy,
    )
    qid = to_qlib_instrument(ik).lower()
    feat = D.features(
        [qid],
        ["$close"],
        start_time=str(market["trading_date"].min()),
        end_time=str(market["trading_date"].max()),
    )
    dq_vals = [float(x) for x in market.sort_values("trading_date")["close"].tolist()]
    q_vals = [float(x) for x in feat.iloc[:, 0].tolist()]
    n = min(len(dq_vals), len(q_vals))
    compare_feature_values(dq_vals[:n], q_vals[:n], atol=1e-8, rtol=1e-6)


def test_artifact_id_deterministic():
    a = compute_dataset_artifact_id(
        bundle_hash="abc",
        segments={"train": {"start": "2024-01-01", "end": "2024-02-01"}},
        label={"code": "fwd_ret"},
    )
    b = compute_dataset_artifact_id(
        bundle_hash="abc",
        segments={"train": {"start": "2024-01-01", "end": "2024-02-01"}},
        label={"code": "fwd_ret"},
    )
    assert a == b
