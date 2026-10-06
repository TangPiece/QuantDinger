"""Golden：两因子组合（相同 / 正交 / IC 加权 / Gram-Schmidt）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import FactorDatasetRecord
from app.services.research_data.factor_lab.combination import (
    CombinationSpec,
    FactorCombinationService,
)
from app.services.research_data.factor_lab.combination.artifact_store import (
    CombinationArtifactStore,
)
from app.services.research_data.registry import LocalJsonRegistry

FID_A = "fds_comb_a"
FID_B = "fds_comb_b"
D1 = date(2024, 7, 1)
D2 = date(2024, 7, 2)


def _ik(i: int) -> str:
    return f"CNStock:{i:03d}"


def identical_panels(n: int = 40) -> tuple[list[dict], list[dict]]:
    """两因子完全相同 → corr≈1。"""
    a, b = [], []
    for i in range(n):
        v = float(i)
        row = {"instrument_key": _ik(i), "trading_date": D1, "value": v}
        a.append(row)
        b.append(dict(row))
    return a, b


def orthogonal_panels(n: int = 40) -> tuple[list[dict], list[dict]]:
    """构造近似正交两列（交替符号 vs 线性趋势）。"""
    a, b = [], []
    for i in range(n):
        a.append(
            {
                "instrument_key": _ik(i),
                "trading_date": D1,
                "value": float(i),
            }
        )
        # 与线性趋势正交的交替列
        b.append(
            {
                "instrument_key": _ik(i),
                "trading_date": D1,
                "value": 1.0 if i % 2 == 0 else -1.0,
            }
        )
    return a, b


def noisy_second_panels(n: int = 40, noise: float = 0.01) -> tuple[list[dict], list[dict]]:
    """第二因子 = 第一因子 + 小噪声 → 正交后第二列与第一列 corr≈0。"""
    a, b = [], []
    for i in range(n):
        v = float(i)
        a.append({"instrument_key": _ik(i), "trading_date": D1, "value": v})
        b.append(
            {
                "instrument_key": _ik(i),
                "trading_date": D1,
                "value": v + noise * (1.0 if i % 2 == 0 else -1.0),
            }
        )
    return a, b


def make_env(tmp_path: Path):
    """本地 Canonical + Registry + Combination Service。"""
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    for fid, href in ((FID_A, "raw_a@1.0.0"), (FID_B, "raw_b@1.0.0")):
        registry.upsert_factor_dataset(
            FactorDatasetRecord(
                factor_dataset_id=fid,
                factor_ref=href,
                factor_hash=f"fh_{fid}",
                dataset_hash=f"dh_{fid}",
                snapshot_id="snap_4h",
                universe_code="CSI300",
                start_date=D1.isoformat(),
                end_date=D2.isoformat(),
                row_count=0,
                layout="long",
            )
        )
    svc = FactorCombinationService(
        store,
        registry,
        artifact_store=CombinationArtifactStore(root=tmp_path / "comb_art"),
    )
    return store, registry, svc


def default_spec(**kw) -> CombinationSpec:
    """默认 EQUAL + RANK；测试可覆盖 min_cs。"""
    base = dict(
        member_factor_dataset_ids=[FID_A, FID_B],
        normalize="RANK",
        weight_method="EQUAL",
        min_cross_section_size=10,
        redundancy_corr_threshold=0.7,
    )
    base.update(kw)
    return CombinationSpec(**base)


def run_with_panels(
    svc: FactorCombinationService,
    panel_a: list[dict],
    panel_b: list[dict],
    spec: CombinationSpec | None = None,
    **meta,
):
    """注入成员面板跑组合。"""
    return svc.run(
        [FID_A, FID_B],
        spec or default_spec(),
        metadata={
            "member_records": {FID_A: panel_a, FID_B: panel_b},
            "force_recompute": True,
            **meta,
        },
    )
