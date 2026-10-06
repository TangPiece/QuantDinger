"""Phase 4B：Factor Computation Engine 验收。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.research_data.contracts import FeatureDefinition, PricePolicy
from app.services.research_data.factor_lab import (
    FactorComputeService,
    PITComputeContext,
    build_compute_plan,
    compute_result_dataset_hash,
    register_factor,
    resolve_dependency_dag,
    select_engine,
)
from app.services.research_data.factor_lab.compute.hash import compute_result_dataset_hash as rd_hash
from app.services.research_data.factor_lab.compute.engines.duckdb_engine import DuckDBFactorEngine
from app.services.research_data.factor_lab.compute.engines.polars_engine import PolarsFactorEngine
from app.services.research_data.factor_lab.dependencies import FactorDependencyError
from app.services.research_data.factor_lab.registry_api import register_factor as reg_factor
from app.services.research_data.registry import LocalJsonRegistry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_lab_compute.golden import (  # noqa: E402
    INSTRUMENTS,
    make_env,
    register_momentum,
    register_roe,
)


def _ctx(days, **kw) -> PITComputeContext:
    base = dict(
        knowledge_time=datetime(2024, 5, 31, 15, 0, 0, tzinfo=timezone.utc),
        snapshot_id="snap_4b",
        start_date=days[0].isoformat(),
        end_date=days[-1].isoformat(),
        exchange="CN",
        universe_code="",
        price_policy=PricePolicy(adjustment="none"),
        canonical_dataset_hash="input_ds_4b",
    )
    base.update(kw)
    return PITComputeContext(**base)


def test_dag_and_cycle(tmp_path):
    _, registry, _, _, _ = make_env(tmp_path)
    register_momentum(registry)
    feat = registry.get_feature("momentum_20d@1.0.0")
    dag = resolve_dependency_dag(feat, registry)
    assert "market:CNStock" in dag.order
    assert dag.root_ref == "momentum_20d@1.0.0"

    with pytest.raises(FactorDependencyError):
        register_factor(
            registry,
            FeatureDefinition(
                code="cyc",
                version="1.0.0",
                name="cyc",
                expression="x",
                dependencies=["factor:cyc@1.0.0"],
            ),
        )


def test_missing_dependency(tmp_path):
    reg = LocalJsonRegistry(root=tmp_path / "r")
    with pytest.raises(FactorDependencyError):
        register_factor(
            reg,
            FeatureDefinition(
                code="x",
                version="1.0.0",
                name="x",
                expression="momentum_20",
                dependencies=["factor:missing@1.0.0"],
            ),
        )


def test_compute_plan_determinism(tmp_path):
    _, registry, _, _, days = make_env(tmp_path)
    feat = register_momentum(registry)
    ctx = _ctx(days)
    p1 = build_compute_plan(feat, ctx, registry)
    p2 = build_compute_plan(feat, ctx, registry)
    assert p1.plan_hash == p2.plan_hash
    assert select_engine(feat) == "quantdinger"


def test_hash_and_reproducibility(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, _, svc, days = make_env(tmp_path)
    register_momentum(registry)
    ctx = _ctx(days)
    meta = {"instruments": INSTRUMENTS, "exchange": "CN"}
    a = svc.run("momentum_20d@1.0.0", ctx, metadata=meta)
    b = svc.run("momentum_20d@1.0.0", ctx, metadata=meta)
    assert a.record.factor_dataset_id == b.record.factor_dataset_id
    assert a.record.dataset_hash == b.record.dataset_hash
    assert compute_result_dataset_hash(a.plan) == a.record.dataset_hash
    assert a.frame.row_count == b.frame.row_count
    assert a.frame.row_count > 0


def test_version_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, _, svc, days = make_env(tmp_path)
    register_momentum(registry, version="1.0.0")
    register_factor(
        registry,
        FeatureDefinition(
            code="momentum_20d",
            version="1.1.0",
            name="Momentum 20D v1.1",
            expression="momentum_10",
            factor_type="TECHNICAL",
            computation_engine="quantdinger",
            dependencies=["market:CNStock"],
            information_policy="NON_PIT",
            price_policy=PricePolicy(adjustment="none"),
        ),
    )
    ctx = _ctx(days)
    meta = {"instruments": INSTRUMENTS}
    r0 = svc.run("momentum_20d@1.0.0", ctx, metadata=meta)
    r1 = svc.run("momentum_20d@1.1.0", ctx, metadata=meta)
    assert r0.record.factor_dataset_id != r1.record.factor_dataset_id
    assert r0.record.factor_hash != r1.record.factor_hash


def test_pit_leakage(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, _, svc, days = make_env(tmp_path)
    register_roe(registry)
    meta = {"instruments": INSTRUMENTS}
    # knowledge before available_time (2024-05-02) → 无值
    early = _ctx(
        days,
        knowledge_time=datetime(2024, 5, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    r_early = svc.run("roe@1.0.0", early, metadata=meta)
    assert r_early.frame.row_count == 0
    # knowledge after available → 有值
    late = _ctx(
        days,
        knowledge_time=datetime(2024, 5, 10, 15, 0, 0, tzinfo=timezone.utc),
    )
    r_late = svc.run("roe@1.0.0", late, metadata=meta)
    assert r_late.frame.row_count > 0


def test_schema_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, _, svc, days = make_env(tmp_path)
    register_momentum(registry)
    res = svc.run(
        "momentum_20d@1.0.0",
        _ctx(days),
        metadata={"instruments": INSTRUMENTS},
    )
    assert res.record.checksum
    assert res.record.storage_uri
    got = registry.get_factor_dataset(res.record.factor_dataset_id)
    assert got.factor_ref == "momentum_20d@1.0.0"
    man_path = Path(got.storage_uri) / "manifest.json"
    assert man_path.is_file()


def test_polars_vs_duckdb(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, query, _, days = make_env(tmp_path)
    feat = register_momentum(registry)
    # 强制 duckdb engine
    feat_d = feat.model_copy(update={"computation_engine": "duckdb", "factor_hash": None})
    from app.services.research_data.factor_lab.hash import compute_factor_hash

    feat_d = feat_d.model_copy(update={"factor_hash": compute_factor_hash(feat_d)})
    registry.upsert_feature(
        FeatureDefinition(
            code="momentum_20d",
            version="duck1",
            name="m",
            expression="momentum_20",
            computation_engine="duckdb",
            dependencies=["market:CNStock"],
            information_policy="NON_PIT",
            price_policy=PricePolicy(adjustment="none"),
        )
    )
    ctx = _ctx(days)
    plan_p = build_compute_plan(feat, ctx, registry)
    plan_p = plan_p.model_copy(
        update={"metadata": {"instruments": INSTRUMENTS}, "engine": "quantdinger"}
    )
    plan_d = build_compute_plan(
        registry.get_feature("momentum_20d@duck1"), ctx, registry
    )
    plan_d = plan_d.model_copy(update={"metadata": {"instruments": INSTRUMENTS}})
    fp = PolarsFactorEngine().compute(plan_p, query=query, registry=registry)
    fd = DuckDBFactorEngine().compute(plan_d, query=query, registry=registry)
    assert fp.row_count > 0 and fd.row_count > 0
    # 对齐比较末值
    mp = {(r["instrument_key"], r["trading_date"]): r["value"] for r in fp.records}
    md = {(r["instrument_key"], r["trading_date"]): r["value"] for r in fd.records}
    common = set(mp) & set(md)
    assert common
    diffs = [abs(mp[k] - md[k]) for k in common]
    assert max(diffs) < 1e-6


def test_level2_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    _, registry, _, svc, days = make_env(tmp_path)
    register_factor(
        registry,
        FeatureDefinition(
            code="l2_imb",
            version="1.0.0",
            name="L2 imb",
            expression="l2_imbalance",
            computation_engine="level2",
            dependencies=["level2:imbalance"],
            information_policy="NON_PIT",
        ),
    )
    import pandas as pd

    panel = pd.DataFrame(
        {
            "instrument_key": ["CNStock:600519", "CNStock:600519"],
            "trading_date": [days[0], days[1]],
            "l2_imbalance": [0.1, 0.2],
        }
    )
    res = svc.run(
        "l2_imb@1.0.0",
        _ctx(days),
        metadata={"l2_panel": panel, "instruments": INSTRUMENTS},
    )
    assert res.frame.row_count == 2
    assert abs(res.frame.records[0]["value"] - 0.1) < 1e-9
