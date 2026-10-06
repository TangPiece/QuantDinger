"""Phase 4H：Factor Combination 验收。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

from app.services.research_data.factor_lab.combination import (
    FactorCombinationError,
    compute_combination_hash,
)
from app.services.research_data.factor_lab.combination.normalize import CSNormalizer
from app.services.research_data.factor_lab.combination.orthogonalize import (
    GramSchmidtOrtho,
)
from app.services.research_data.factor_lab.combination.weighting import WeightSolver

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_lab_combination.golden import (  # noqa: E402
    FID_A,
    FID_B,
    default_spec,
    identical_panels,
    make_env,
    noisy_second_panels,
    orthogonal_panels,
    run_with_panels,
)


def test_identical_factors_corr_and_redundancy(tmp_path):
    """两因子完全相同 → corr≈1、冗余对命中、CORR_ADJUSTED 降权直觉。"""
    _, registry, svc = make_env(tmp_path)
    a, b = identical_panels(40)
    r = run_with_panels(
        svc,
        a,
        b,
        default_spec(
            weight_method="CORR_ADJUSTED",
            member_ic={FID_A: 0.06, FID_B: 0.06},
            normalize="ZSCORE",
        ),
    )
    mat = r.frames.metadata["corr_summary"]["matrix"]
    assert abs(mat[FID_A][FID_B] - 1.0) < 1e-9
    assert any(
        {p.factor_i, p.factor_j} == {FID_A, FID_B} for p in r.frames.redundancy_pairs
    )
    # 完全相关时 CORR_ADJUSTED 仍对称等权（同 IC）
    wmap = {w.factor_dataset_id: w.weight for w in r.frames.weights}
    assert abs(wmap[FID_A] - 0.5) < 1e-9
    assert abs(wmap[FID_B] - 0.5) < 1e-9
    assert registry.get_factor_combination(r.combination_hash)


def test_equal_orthogonal_zscore_composite(tmp_path):
    """正交两因子 EQUAL + ZSCORE → composite = 0.5(z1+z2)。"""
    _, _, svc = make_env(tmp_path)
    a, b = orthogonal_panels(40)
    spec = default_spec(normalize="ZSCORE", weight_method="EQUAL")
    r = run_with_panels(svc, a, b, spec)
    # 用引擎路径复核：normalize 后再 0.5 加权
    from app.services.research_data.factor_lab.combination.align import (
        CrossSectionAligner,
    )

    aligned = CrossSectionAligner().align(
        {FID_A: a, FID_B: b}, spec
    )
    norm = CSNormalizer().normalize(aligned, spec)
    for row, c in zip(norm, r.frames.composite_rows):
        expect = 0.5 * (row.values[FID_A] + row.values[FID_B])
        assert abs(c.composite - expect) < 1e-9


def test_ic_weight_two_thirds(tmp_path):
    """IC_WEIGHT：ic=(0.06,0.03) → w≈(2/3,1/3)。"""
    _, _, svc = make_env(tmp_path)
    a, b = orthogonal_panels(40)
    r = run_with_panels(
        svc,
        a,
        b,
        default_spec(
            weight_method="IC_WEIGHT",
            member_ic={FID_A: 0.06, FID_B: 0.03},
        ),
    )
    wmap = {w.factor_dataset_id: w.weight for w in r.frames.weights}
    assert abs(wmap[FID_A] - 2.0 / 3.0) < 1e-9
    assert abs(wmap[FID_B] - 1.0 / 3.0) < 1e-9


def test_ic_weight_missing_hard_fail(tmp_path):
    _, _, svc = make_env(tmp_path)
    a, b = orthogonal_panels(20)
    with pytest.raises(FactorCombinationError):
        run_with_panels(
            svc,
            a,
            b,
            default_spec(weight_method="IC_WEIGHT", member_ic={FID_A: 0.06}),
        )


def test_orthogonalize_removes_collinearity(tmp_path):
    """第二因子=第一+噪声 → 正交后第二列与第一列 corr≈0。"""
    _, _, svc = make_env(tmp_path)
    a, b = noisy_second_panels(40, noise=0.05)
    spec = default_spec(normalize="ZSCORE", weight_method="ORTHOGONALIZE")
    r = run_with_panels(svc, a, b, spec)
    # 从 composite member_values（正交列）算相关
    xs = [row.member_values[FID_A] for row in r.frames.composite_rows]
    ys = [row.member_values[FID_B] for row in r.frames.composite_rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    corr = num / (dx * dy) if dx and dy else 0.0
    assert abs(corr) < 1e-6


def test_drop_row_and_min_cs(tmp_path):
    _, _, svc = make_env(tmp_path)
    a, b = identical_panels(40)
    # 去掉 B 中一半票 → DROP_ROW 后仅剩 20；min_cs=30 应失败
    b_half = b[:20]
    with pytest.raises(FactorCombinationError):
        run_with_panels(
            svc,
            a,
            b_half,
            default_spec(min_cross_section_size=30),
        )
    # min_cs=10 应成功且行数=20
    r = run_with_panels(
        svc, a, b_half, default_spec(min_cross_section_size=10)
    )
    assert len(r.frames.composite_rows) == 20


def test_hash_repro_manifest_and_raw_immutable(tmp_path):
    _, registry, svc = make_env(tmp_path)
    a, b = orthogonal_panels(40)
    spec = default_spec()
    r1 = run_with_panels(svc, a, b, spec)
    r2 = run_with_panels(svc, a, b, spec)
    assert r1.combination_hash == r2.combination_hash
    h = compute_combination_hash(
        spec, member_hashes={FID_A: f"dh_{FID_A}", FID_B: f"dh_{FID_B}"}
    )
    assert h == r1.combination_hash
    art = Path(r1.summary.storage_uri)
    assert (art / "manifest.json").is_file()
    assert (art / "summary.json").is_file()
    # 成员 Dataset 不变
    assert registry.get_factor_dataset(FID_A).factor_ref == "raw_a@1.0.0"
    assert registry.get_factor_dataset(FID_B).factor_ref == "raw_b@1.0.0"
    # composite 可被 registry get
    comp = registry.get_factor_dataset(r1.composite_factor_dataset_id)
    assert comp.factor_ref.startswith("composite@c_")


def test_weight_solver_unit():
    """单元：CORR_ADJUSTED 对高相关成员降权。"""
    spec = default_spec(
        weight_method="CORR_ADJUSTED",
        member_ic={FID_A: 0.06, FID_B: 0.06},
    )
    # A 与 B 高相关 vs 假设第三因子（此处两因子对称）
    mat = {
        FID_A: {FID_A: 1.0, FID_B: 0.9},
        FID_B: {FID_A: 0.9, FID_B: 1.0},
    }
    ws = WeightSolver().solve(spec, corr_matrix=mat)
    wmap = {w.factor_dataset_id: w.weight for w in ws}
    assert abs(wmap[FID_A] - wmap[FID_B]) < 1e-9


def test_gram_schmidt_unit():
    """单元：Gram-Schmidt 后列正交。"""
    a, b = noisy_second_panels(30, noise=0.02)
    spec = default_spec(normalize="ZSCORE", weight_method="ORTHOGONALIZE")
    from app.services.research_data.factor_lab.combination.align import (
        CrossSectionAligner,
    )

    aligned = CrossSectionAligner().align({FID_A: a, FID_B: b}, spec)
    norm = CSNormalizer().normalize(aligned, spec)
    rows = GramSchmidtOrtho().combine(norm, spec)
    xs = [r.member_values[FID_A] for r in rows]
    ys = [r.member_values[FID_B] for r in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    assert abs(num / (dx * dy)) < 1e-6
