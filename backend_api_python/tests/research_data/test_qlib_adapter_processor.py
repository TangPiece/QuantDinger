"""Phase 2A：ProcessorAdapter 白名单。"""

from __future__ import annotations

import pytest

from app.services.research_data.contracts import ProcessorDefinition
from app.services.research_data.qlib_adapter import (
    ProcessorAdapter,
    UnsupportedProcessorError,
    builtin_cs_zscore_processor,
    builtin_identity_processor,
)


def test_identity_and_cs_zscore(golden_qlib_env):
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_identity_processor())
    registry.upsert_processor(builtin_cs_zscore_processor())
    pa = ProcessorAdapter(registry)

    ident = pa.resolve_definition("identity@1")
    assert ident is not None
    learn, infer = pa.build_handler_processors(ident)
    assert learn == []
    assert infer == []

    cs = pa.resolve_definition("cs_zscore@1")
    learn2, infer2 = pa.build_handler_processors(cs)
    assert len(learn2) == 1
    assert learn2[0]["class"] == "CSZScoreNorm"
    assert learn2 == infer2  # 训练/推理同一配置

    assert pa.resolve_definition(None) is None
    assert pa.build_handler_processors(None) == ([], [])


def test_unknown_processor_step_fails():
    pa = ProcessorAdapter()
    bad = ProcessorDefinition(
        code="bad",
        version="1",
        pipeline=[{"class": "UnknownMagicNorm"}],
    )
    with pytest.raises(UnsupportedProcessorError):
        pa.build_handler_processors(bad)


def test_registry_roundtrip(golden_qlib_env):
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_identity_processor())
    got = registry.get_processor("identity@1")
    assert got.code == "identity"
    assert got.pipeline == []
