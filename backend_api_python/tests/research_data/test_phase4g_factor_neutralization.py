"""Phase 4G：Factor Neutralization 验收。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

from app.services.research_data.factor_lab.neutralization import (
    FactorNeutralizationError,
    NeutralizationSpec,
    compute_neutralization_hash,
)
from app.services.research_data.factor_lab.neutralization.exposure import (
    InjectedExposureProvider,
    knowledge_time_for,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor_lab_neutralization.golden import (  # noqa: E402
    AT_FUTURE,
    AT_OK,
    D1,
    FID,
    default_spec,
    make_env,
    size_industry_panel,
)


def _run(svc, factors, exposures, spec=None, **meta):
    return svc.run(
        FID,
        spec or default_spec(),
        metadata={
            "factor_records": factors,
            "exposure_rows": exposures,
            "force_recompute": True,
            **meta,
        },
    )


def test_size_neutralization_recovers_alpha(tmp_path):
    """Factor=2*log(mcap)+Alpha → residual ≈ Alpha（相关去 Size）。"""
    _, registry, svc = make_env(tmp_path)
    factors, exposures, alphas = size_industry_panel(40)
    # 仅 SIZE
    ex_size = [e for e in exposures if e["exposure_code"] == "SIZE"]
    r = _run(svc, factors, ex_size, default_spec(targets=["SIZE"]))
    neu = {
        x.instrument_key: x.neutralized_factor
        for x in r.frames.factor_rows
        if x.neutralized_factor is not None
    }
    assert len(neu) == 40
    # residual 与 Alpha 高度相关（截距吸收常数后仍近似线性）
    a = alphas
    n = [neu[f"CNStock:{i:03d}"] for i in range(40)]
    # demean 后相关
    ma, mn = sum(a) / len(a), sum(n) / len(n)
    num = sum((x - ma) * (y - mn) for x, y in zip(a, n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    dn = math.sqrt(sum((y - mn) ** 2 for y in n))
    corr = num / (da * dn)
    assert corr > 0.95
    # residual 接近 Alpha（允许数值误差）
    assert max(abs(n[i] - (a[i] - ma)) for i in range(40)) < 1e-6 or corr > 0.99
    # Size corr after ≈ 0
    size_diag = next(
        d
        for d in r.frames.diagnostics
        if d.exposure_code == "SIZE" and d.status == "OK"
    )
    assert abs(size_diag.correlation_after or 0) < 0.05
    assert (size_diag.correlation_before or 0) > 0.5
    assert size_diag.r_squared is not None and size_diag.r_squared > 0.9
    assert registry.get_factor_neutralization(r.neutralization_hash)
    assert r.neutralized_factor_dataset_id


def test_size_plus_industry(tmp_path):
    _, _, svc = make_env(tmp_path)
    factors, exposures, _ = size_industry_panel(40)
    r = _run(
        svc,
        factors,
        exposures,
        default_spec(targets=["SIZE", "INDUSTRY"]),
    )
    assert any(d.exposure_code == "INDUSTRY" for d in r.frames.diagnostics)
    assert any(x.neutralized_factor is not None for x in r.frames.factor_rows)


def test_pit_future_size_invisible(tmp_path):
    """available_time > knowledge_time 的 SIZE 不得进入 D1 回归。"""
    _, _, svc = make_env(tmp_path)
    factors, exposures, _ = size_industry_panel(20)
    # 污染：全部 SIZE 改为未来 available_time
    bad = []
    for e in exposures:
        if e["exposure_code"] != "SIZE":
            continue
        bad.append({**e, "available_time": AT_FUTURE})
    kt = knowledge_time_for(D1)
    assert AT_FUTURE > kt
    with pytest.raises(FactorNeutralizationError):
        _run(
            svc,
            factors,
            bad,
            default_spec(targets=["SIZE"], min_cross_section_size=10),
        )


def test_beta_hard_fail_without_injection(tmp_path):
    _, _, svc = make_env(tmp_path)
    factors, exposures, _ = size_industry_panel(20)
    with pytest.raises(FactorNeutralizationError):
        _run(
            svc,
            factors,
            [e for e in exposures if e["exposure_code"] == "SIZE"],
            default_spec(targets=["SIZE", "BETA"]),
        )


def test_insufficient_sample(tmp_path):
    _, _, svc = make_env(tmp_path)
    factors, exposures, _ = size_industry_panel(5)
    with pytest.raises(FactorNeutralizationError):
        _run(
            svc,
            factors,
            [e for e in exposures if e["exposure_code"] == "SIZE"],
            default_spec(targets=["SIZE"], min_cross_section_size=30),
        )


def test_raw_factor_immutable_and_hash(tmp_path):
    _, registry, svc = make_env(tmp_path)
    factors, exposures, _ = size_industry_panel(40)
    ex_size = [e for e in exposures if e["exposure_code"] == "SIZE"]
    spec = default_spec(targets=["SIZE"])
    r1 = _run(svc, factors, ex_size, spec)
    r2 = _run(svc, factors, ex_size, spec)
    assert r1.neutralization_hash == r2.neutralization_hash
    h = compute_neutralization_hash(spec, factor_dataset_hash="dh_4g")
    assert h == r1.neutralization_hash
    # raw registry 仍在
    assert registry.get_factor_dataset(FID).factor_ref == "raw_alpha@1.0.0"
    # neutralized 是新 id
    assert r1.neutralized_factor_dataset_id != FID
    neut = registry.get_factor_dataset(r1.neutralized_factor_dataset_id)
    assert neut.factor_ref.startswith("neut_factor@")
    art = Path(r1.summary.storage_uri)
    assert (art / "manifest.json").is_file()


def test_partial_strength_rejected():
    with pytest.raises(Exception):
        NeutralizationSpec(
            factor_dataset_id=FID,
            strength="PARTIAL",  # type: ignore[arg-type]
        )


def test_injected_provider_pit_filter():
    rows = [
        {
            "instrument_key": "CNStock:000",
            "trading_date": D1,
            "exposure_code": "SIZE",
            "exposure_value": 1e9,
            "available_time": AT_OK,
        },
        {
            "instrument_key": "CNStock:001",
            "trading_date": D1,
            "exposure_code": "SIZE",
            "exposure_value": 2e9,
            "available_time": AT_FUTURE,
        },
    ]
    p = InjectedExposureProvider(rows)
    got = p.load_for_date(
        D1,
        ["CNStock:000", "CNStock:001"],
        default_spec(targets=["SIZE"]),
    )
    keys = {g.instrument_key for g in got}
    assert "CNStock:000" in keys
    assert "CNStock:001" not in keys
