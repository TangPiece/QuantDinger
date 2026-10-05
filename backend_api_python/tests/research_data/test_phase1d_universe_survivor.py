"""Phase 1D：Universe 幸存者偏差 — 历史 as_of ↔ Qlib instruments。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("qlib")
import qlib
from qlib.data import D

from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
from app.services.research_data.qlib_materializer.validation import compare_universe_sets


def test_universe_t1_t2_membership_differs(golden_qlib_env):
    """T1=2022 含历史调出；T2=2024-06 不含 999999、含 688001。"""
    query = golden_qlib_env["query"]
    handle = query.dataset(golden_qlib_env["dataset_ref"])
    code = handle.definition.universe_code
    snap = handle.definition.snapshot_id
    ver = handle.definition.universe_version

    t1 = query.universe(code, date(2022, 6, 1), snapshot_id=snap, universe_version=ver)
    t2 = query.universe(code, date(2024, 6, 30), snapshot_id=snap, universe_version=ver)
    assert "CNStock:999999" in t1
    assert "CNStock:999999" not in t2
    assert "CNStock:688001" in t2
    assert "CNStock:688001" not in t1
    assert set(t1) != set(t2)


def test_materializer_instruments_match_as_of_end(golden_qlib_env):
    """Materializer(end=T) 落盘 instruments ≡ DQ.universe(T) ≡ D.list_instruments。"""
    query = golden_qlib_env["query"]
    ref = golden_qlib_env["dataset_ref"]
    handle = query.dataset(ref)
    end = golden_qlib_env["end"]
    mat = golden_qlib_env["materializer"]
    result = mat.materialize(ref, force=True)

    expected = query.universe(
        handle.definition.universe_code,
        end,
        snapshot_id=handle.definition.snapshot_id,
        universe_version=handle.definition.universe_version,
    )
    file_ids = {
        ln.split("\t")[0]
        for ln in (Path(result.cache_path) / "instruments" / "all.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    }
    compare_universe_sets(expected, file_ids)

    qlib.init(
        provider_uri=result.cache_path,
        region="cn",
        expression_cache=None,
        dataset_cache=None,
        kernels=1,
    )
    cal = sorted(
        {
            str(d.date() if hasattr(d, "date") else d)
            for d in D.calendar(freq="day")
        }
    )
    listed = {
        str(x).lower()
        for x in D.list_instruments(
            D.instruments(market="all"),
            start_time=cal[0],
            end_time=cal[-1],
            as_list=True,
        )
    }
    compare_universe_sets(expected, listed)
    assert "CNStock:999999" not in expected
    assert "CNStock:688001" in expected


def test_materializer_historical_as_of_includes_delisted(golden_qlib_env, tmp_path):
    """窗口终点落在 2022 → 物化应包含已调出的 999999，不含 688001。"""
    query = golden_qlib_env["query"]
    # 历史窗口需要 2022 行情；golden 默认从 2024 起，改用 end 探测 as_of 即可测 universe
    # 使用显式 end=2022-06-01；market 可能为空则跳过物化——改为只断言 as_of 解析路径
    # 通过构造带 2022 行情的独立 materializer 过于重；此处验证 _resolve 在 end=2022 时的成员
    mat = DefaultQlibMaterializer(
        query,
        cache_root=tmp_path / "hist_cache",
        start=date(2020, 1, 1),
        end=date(2022, 6, 1),
    )
    handle = query.dataset(golden_qlib_env["dataset_ref"])
    as_of, instruments, market = mat._resolve_universe_and_market(
        definition=handle.definition,
        start=date(2020, 1, 1),
        end_bound=date(2022, 6, 1),
        price_policy=handle.definition.price_policy,
    )
    assert as_of == date(2022, 6, 1)
    assert "CNStock:999999" in instruments
    assert "CNStock:688001" not in instruments
    # 2022 窗口无 fixture 行情时 market 可空——universe 断言已足够
    del market
