"""Phase 2A：QlibRuntime 进程级 init 封装。"""

from __future__ import annotations

import pytest

pytest.importorskip("qlib")
from qlib.data import D

from app.services.research_data.qlib_adapter import QlibRuntime, QlibRuntimeError


def test_runtime_activate_and_features(golden_qlib_env):
    mat = golden_qlib_env["materializer"]
    result = mat.materialize(golden_qlib_env["dataset_ref"], force=True)
    rt = QlibRuntime()
    assert rt.is_active is False
    with pytest.raises(QlibRuntimeError):
        rt.require_active()

    rt.activate(result.cache_path, kernels=1)
    assert rt.is_active is True
    assert rt.provider_uri is not None

    # 经 Runtime 激活后 D.features 可读
    df = D.features(["sz000001"], ["$close"], start_time="2024-01-01", end_time="2024-06-01")
    assert len(df) > 0


def test_runtime_session_context(golden_qlib_env):
    mat = golden_qlib_env["materializer"]
    result = mat.materialize(golden_qlib_env["dataset_ref"], force=True)
    rt = QlibRuntime()
    with rt.session(result.cache_path, kernels=1) as active:
        assert active.is_active
        cal = D.calendar(start_time="2024-01-01", end_time="2024-06-01", freq="day")
        assert len(cal) >= 1
