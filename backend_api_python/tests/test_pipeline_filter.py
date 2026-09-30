"""pipeline 默认标的过滤行为测试（A 股+基金保留，可转债/B股过滤）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.level2_ingest import config
from app.services.level2_ingest.pipeline import _matches, process_7z


@pytest.fixture
def seven_z_path() -> Path:
    """使用已缓存 manifest 的交易日归档。"""
    path = config.DATA_ROOT / "20260818.7z"
    if not path.exists():
        pytest.skip(f"测试数据不存在: {path}")
    manifest_path = config.local_manifest_path("20260818")
    if not manifest_path.exists():
        pytest.skip(f"manifest 未生成: {manifest_path}")
    return path


def test_matches_keeps_fund_by_default() -> None:
    """equities_only=True 时场内基金仍匹配。"""
    assert _matches("159919.SZ", "行情", None, None, equities_only=True) is True
    assert _matches("510300.SH", "逐笔成交", None, None, equities_only=True) is True


def test_matches_filters_bond_and_b_share() -> None:
    """equities_only=True 时仍过滤可转债与 B 股。"""
    assert _matches("123138.SZ", "行情", None, None, equities_only=True) is False
    assert _matches("110075.SH", "行情", None, None, equities_only=True) is False
    assert _matches("900901.SH", "行情", None, None, equities_only=True) is False


def test_equities_only_filters_non_default(seven_z_path: Path) -> None:
    """默认保留 A 股+基金；仍过滤可转债/B股等（filtered > 0 且小于全量差）。"""
    stats = process_7z(
        seven_z_path,
        dry_run=True,
        skip_existing=False,
        equities_only=True,
    )
    assert stats["filtered_non_equity"] > 0
    assert stats["total"] > 10_000
    # 纳入基金后，被过滤的应明显少于「仅 A 股」时代（原先 >5000）
    assert stats["filtered_non_equity"] < 5_000


def test_all_symbols_includes_non_default(seven_z_path: Path) -> None:
    """equities_only=False（--all-symbols）时包含全部标的。"""
    stats_eq = process_7z(
        seven_z_path,
        dry_run=True,
        skip_existing=False,
        equities_only=True,
    )
    stats_all = process_7z(
        seven_z_path,
        dry_run=True,
        skip_existing=False,
        equities_only=False,
    )
    assert stats_all["filtered_non_equity"] == 0
    assert stats_all["total"] > stats_eq["total"]
    assert stats_all["total"] == stats_eq["total"] + stats_eq["filtered_non_equity"]
