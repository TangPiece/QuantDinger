"""Phase 4A：Factor Lab Foundation 验收。"""

from __future__ import annotations

import pytest

from app.services.research_data.contracts import FeatureDefinition, PricePolicy
from app.services.research_data.factor_lab import (
    FACTOR_LAB_CONTRACT_VERSION,
    FactorDatasetArtifactStore,
    FactorManifestError,
    build_factor_dataset_record,
    build_manifest,
    compute_factor_dataset_id,
    compute_factor_hash,
    get_factor,
    is_backtest_eligible,
    parse_dependency,
    recommend_layout,
    register_factor,
    register_factor_dataset,
    validate_for_backtest,
    validate_manifest,
)
from app.services.research_data.factor_lab.dependencies import FactorDependencyError
from app.services.research_data.registry import (
    FeatureImmutabilityError,
    LocalJsonRegistry,
)
from app.services.research_data.schemas import SCHEMA_VERSION_FACTOR_WIDE


def _feat(**overrides) -> FeatureDefinition:
    base = dict(
        code="momentum_20d",
        version="1.0.0",
        name="Momentum 20D",
        expression="close / Ref(close, 20) - 1",
        description="20-day momentum",
        factor_type="TECHNICAL",
        computation_engine="quantdinger",
        engine_version="1",
        frequency="1d",
        dependencies=["market:CNStock"],
        information_policy="NON_PIT",
        schema_version="factor_daily_long@1",
        backend="r2_factor",
        price_policy=PricePolicy(adjustment="post"),
    )
    base.update(overrides)
    return FeatureDefinition(**base)


def test_factor_hash_determinism():
    a = _feat()
    b = _feat()
    assert compute_factor_hash(a) == compute_factor_hash(b)
    c = _feat(expression="close / Ref(close, 21) - 1")
    assert compute_factor_hash(a) != compute_factor_hash(c)


def test_version_immutability(tmp_path):
    reg = LocalJsonRegistry(root=tmp_path / "registry")
    f1 = register_factor(reg, _feat())
    assert f1.factor_hash
    # 同内容幂等
    register_factor(reg, _feat())
    # 改 expression 同 version → 拒
    with pytest.raises(FeatureImmutabilityError):
        register_factor(reg, _feat(expression="close / Ref(close, 10) - 1"))
    # bump version OK
    f2 = register_factor(reg, _feat(version="1.1.0", expression="close / Ref(close, 10) - 1"))
    assert f2.version == "1.1.0"
    assert f2.factor_hash != f1.factor_hash


def test_dependency_validation(tmp_path):
    reg = LocalJsonRegistry(root=tmp_path / "registry")
    with pytest.raises(FactorDependencyError):
        parse_dependency("invalidtype:x")
    d = parse_dependency("market:CNStock")
    assert d.dependency_type == "market"
    # factor 依赖须存在
    register_factor(reg, _feat(code="base_mom", version="1.0.0"))
    with pytest.raises(FactorDependencyError):
        register_factor(
            reg,
            _feat(
                code="child",
                version="1.0.0",
                dependencies=["factor:missing@1.0.0"],
            ),
        )
    # 自依赖环
    with pytest.raises(FactorDependencyError):
        register_factor(
            reg,
            _feat(
                code="selfx",
                version="1.0.0",
                dependencies=["factor:selfx@1.0.0"],
            ),
        )


def test_factor_dataset_id_reproducible(tmp_path):
    reg = LocalJsonRegistry(root=tmp_path / "registry")
    feat = register_factor(reg, _feat())
    r1 = build_factor_dataset_record(
        feat,
        dataset_hash="ds_abc",
        snapshot_id="snap_1",
        start_date="2024-01-01",
        end_date="2024-12-31",
        universe_code="CSI300",
        layout="long",
    )
    r2 = build_factor_dataset_record(
        feat,
        dataset_hash="ds_abc",
        snapshot_id="snap_1",
        start_date="2024-01-01",
        end_date="2024-12-31",
        universe_code="CSI300",
        layout="long",
    )
    assert r1.factor_dataset_id == r2.factor_dataset_id
    assert r1.factor_dataset_id == compute_factor_dataset_id(
        factor_hash=feat.factor_hash or "",
        dataset_hash="ds_abc",
        snapshot_id="snap_1",
        universe_code="CSI300",
        frequency="1d",
        start_date="2024-01-01",
        end_date="2024-12-31",
        layout="long",
    )
    register_factor_dataset(reg, r1)
    got = reg.get_factor_dataset(r1.factor_dataset_id)
    assert got.factor_ref == "momentum_20d@1.0.0"


def test_pit_policy_gate(tmp_path):
    reg = LocalJsonRegistry(root=tmp_path / "registry")
    unknown = register_factor(
        reg, _feat(code="u1", information_policy="UNKNOWN")
    )
    assert validate_for_backtest(unknown) is False
    assert is_backtest_eligible(reg, "u1@1.0.0") is False

    pit_bad = register_factor(
        reg,
        _feat(
            code="roe_bad",
            version="1.0.0",
            factor_type="FUNDAMENTAL",
            information_policy="PIT_SAFE",
            dependencies=["market:CNStock"],  # 缺 fundamental
        ),
    )
    assert validate_for_backtest(pit_bad) is False

    pit_ok = register_factor(
        reg,
        _feat(
            code="roe",
            version="1.0.0",
            factor_type="FUNDAMENTAL",
            information_policy="PIT_SAFE",
            dependencies=["fundamental:roe", "market:CNStock"],
        ),
    )
    assert validate_for_backtest(pit_ok) is True


def test_manifest_validation(tmp_path):
    reg = LocalJsonRegistry(root=tmp_path / "registry")
    feat = register_factor(reg, _feat())
    rec = build_factor_dataset_record(
        feat,
        dataset_hash="ds",
        snapshot_id="snap",
        start_date="2024-01-01",
        end_date="2024-06-01",
        universe_code="CSI300",
    )
    man = build_manifest(feat, rec, checksum="abc", row_count=10)
    validate_manifest(man)
    store = FactorDatasetArtifactStore(root=tmp_path / "art")
    art = store.write_manifest(man, record=rec)
    assert art.artifact_type == "factor_dataset"
    assert (tmp_path / "art" / "qd" / "dataset" / "factor" / rec.factor_dataset_id / "manifest.json").is_file() or (
        store.dir_for(rec.factor_dataset_id) / "manifest.json"
    ).is_file()

    with pytest.raises(FactorManifestError):
        validate_manifest({"factor_code": "x"})  # 缺大量字段


def test_no_trading_factor_import():
    """研究 factor_lab 不得导入交易侧 factors 包。"""
    import sys

    import app.services.research_data.factor_lab  # noqa: F401

    # 加载 factor_lab 后，交易侧 factors 不应被连带 import
    assert "app.services.factors" not in sys.modules
    assert "app.services.factors.registry" not in sys.modules


def test_layout_and_wide_schema():
    assert recommend_layout(factor_type="FUNDAMENTAL") == "long"
    assert recommend_layout(factor_type="TECHNICAL", n_columns=20) == "wide"
    assert SCHEMA_VERSION_FACTOR_WIDE == "factor_daily_wide@1"
    assert FACTOR_LAB_CONTRACT_VERSION.startswith("qd_factor_lab")


def test_get_factor_spec(tmp_path):
    reg = LocalJsonRegistry(root=tmp_path / "registry")
    register_factor(reg, _feat())
    spec = get_factor(reg, "momentum_20d@1.0.0")
    assert spec.factor_ref == "momentum_20d@1.0.0"
    assert spec.factor_type == "TECHNICAL"
