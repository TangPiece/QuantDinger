"""Golden：Factor = 2 × log(mcap) + Alpha → neutralized ≈ Alpha。"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import FactorDatasetRecord
from app.services.research_data.factor_lab.neutralization import (
    FactorNeutralizationService,
    NeutralizationSpec,
)
from app.services.research_data.factor_lab.neutralization.artifact_store import (
    NeutralizationArtifactStore,
)
from app.services.research_data.registry import LocalJsonRegistry

FID = "fds_golden_4g"
D1 = date(2024, 6, 3)
D2 = date(2024, 6, 4)
# 收盘 KT 之前：可见
AT_OK = datetime(2024, 6, 3, 6, 0, 0, tzinfo=timezone.utc)
# D1 收盘之后：对 D1 不可见（PIT）
AT_FUTURE = datetime(2024, 6, 3, 8, 0, 0, tzinfo=timezone.utc)


def size_industry_panel(n: int = 40) -> tuple[list[dict], list[dict], list[float]]:
    """构造截面：mcap 递增；Alpha 与 Size 正交（交替符号），Factor=2*log(mcap)+Alpha。"""
    factors: list[dict] = []
    exposures: list[dict] = []
    alphas: list[float] = []
    for i in range(n):
        ik = f"CNStock:{i:03d}"
        mcap = 1e9 * (i + 1)
        # 交替 Alpha，避免与 log(mcap) 共线被回归吸走
        alpha = 0.1 if i % 2 == 0 else -0.1
        alphas.append(alpha)
        log_m = math.log(mcap)
        factors.append(
            {
                "instrument_key": ik,
                "trading_date": D1,
                "value": 2.0 * log_m + alpha,
            }
        )
        exposures.append(
            {
                "instrument_key": ik,
                "trading_date": D1,
                "exposure_code": "SIZE",
                "exposure_value": mcap,
                "available_time": AT_OK,
            }
        )
        ind = "INDUSTRY:BANK" if i % 2 == 0 else "INDUSTRY:TECH"
        exposures.append(
            {
                "instrument_key": ik,
                "trading_date": D1,
                "exposure_code": ind,
                "exposure_value": 1.0,
                "available_time": AT_OK,
            }
        )
    return factors, exposures, alphas


def make_env(tmp_path: Path):
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    registry.upsert_factor_dataset(
        FactorDatasetRecord(
            factor_dataset_id=FID,
            factor_ref="raw_alpha@1.0.0",
            factor_hash="fh_4g",
            dataset_hash="dh_4g",
            snapshot_id="snap_4g",
            universe_code="CSI300",
            start_date=D1.isoformat(),
            end_date=D2.isoformat(),
            row_count=0,
            layout="long",
        )
    )
    svc = FactorNeutralizationService(
        store,
        registry,
        artifact_store=NeutralizationArtifactStore(root=tmp_path / "neut_art"),
    )
    return store, registry, svc


def default_spec(**kw) -> NeutralizationSpec:
    base = dict(
        factor_dataset_id=FID,
        method="REGRESSION",
        targets=["SIZE"],
        size_transform="LOG",
        min_cross_section_size=10,
        include_intercept=True,
        exposure_dataset_versions={"SIZE": "injected@1"},
    )
    base.update(kw)
    return NeutralizationSpec(**base)
