"""Phase 2C：Processor 白名单 / immutability / fit 注入 / hash。"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.research_data.contracts import DatasetDefinition, ProcessorDefinition
from app.services.research_data.ingest.build_golden import GOLDEN_DATASET_CODE
from app.services.research_data.qlib_adapter import (
    ProcessorAdapter,
    QlibAdapter,
    QlibAdapterError,
    ResearchDatasetSpec,
    SegmentRange,
    SegmentSpec,
    UnsupportedProcessorError,
    VersionResolver,
    builtin_cs_zscore_processor,
    builtin_identity_processor,
    builtin_qd_standard_processor,
    compute_pipeline_digest,
    inject_fit_window,
    qlib_class_needs_fit,
)
from app.services.research_data.registry import ProcessorImmutabilityError


def _segments() -> SegmentSpec:
    return SegmentSpec(
        train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
        test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
    )


def test_whitelist_five_steps_compile():
    """Dropna / Fillna / Winsorize / CSZScore / MinMax 均可映射。"""
    pa = ProcessorAdapter()
    proc = ProcessorDefinition(
        code="all_steps",
        version="1",
        pipeline=[
            {"class": "DropnaProcessor"},
            {"class": "Fillna", "kwargs": {"fill_value": 0}},
            {"class": "Winsorize"},
            {"class": "CSZScoreNorm"},
            {"class": "MinMaxNorm"},
        ],
    )
    learn, infer = pa.build_handler_processors(proc)
    assert learn == infer
    classes = [s["class"] for s in learn]
    assert classes == [
        "DropnaProcessor",
        "Fillna",
        "RobustZScoreNorm",
        "CSZScoreNorm",
        "MinMaxNorm",
    ]
    assert pa.definition_needs_fit(proc) is True
    assert qlib_class_needs_fit("RobustZScoreNorm")
    assert qlib_class_needs_fit("MinMaxNorm")
    assert not qlib_class_needs_fit("CSZScoreNorm")
    assert not qlib_class_needs_fit("Fillna")


def test_unknown_step_rejected():
    pa = ProcessorAdapter()
    bad = ProcessorDefinition(
        code="bad",
        version="1",
        pipeline=[{"class": "Alpha158Something"}],
    )
    with pytest.raises(UnsupportedProcessorError):
        pa.build_handler_processors(bad)


def test_inject_fit_only_on_fit_steps():
    """Fit 窗只注入 RobustZScore / MinMax，不注入 Fillna / CSZScore。"""
    steps = [
        {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
        {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature"}},
        {"class": "CSZScoreNorm", "kwargs": {"fields_group": "feature"}},
        {"class": "MinMaxNorm", "kwargs": {"fields_group": "feature"}},
    ]
    out = inject_fit_window(steps, "2024-01-01", "2024-02-29")
    assert "fit_start_time" not in out[0]["kwargs"]
    assert out[1]["kwargs"]["fit_start_time"] == "2024-01-01"
    assert out[1]["kwargs"]["fit_end_time"] == "2024-02-29"
    assert "fit_start_time" not in out[2]["kwargs"]
    assert out[3]["kwargs"]["fit_end_time"] == "2024-02-29"


def test_processor_immutability(golden_qlib_env):
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_qd_standard_processor())
    registry.upsert_processor(builtin_qd_standard_processor())  # 幂等 OK

    mutated = ProcessorDefinition(
        code="qd_standard",
        version="1",
        pipeline=[{"class": "CSZScoreNorm"}],  # 改内容
    )
    with pytest.raises(ProcessorImmutabilityError):
        registry.upsert_processor(mutated)


def test_pipeline_digest_changes_bundle_hash(golden_qlib_env):
    """同 ref 不同 pipeline 内容 → digest / bundle_hash 不同（模拟解析层）。"""
    d1 = compute_pipeline_digest(
        [{"class": "CSZScoreNorm", "kwargs": {"fields_group": "feature"}}]
    )
    d2 = compute_pipeline_digest(
        [
            {"class": "Fillna", "kwargs": {"fields_group": "feature", "fill_value": 0}},
            {"class": "CSZScoreNorm", "kwargs": {"fields_group": "feature"}},
        ]
    )
    assert d1 != d2
    assert d1 != "none"

    query = golden_qlib_env["query"]
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_cs_zscore_processor())
    registry.upsert_processor(builtin_qd_standard_processor())

    handle = query.dataset(golden_qlib_env["dataset_ref"])
    base = handle.definition

    def _upsert(code_ver: str, processor_ref: str) -> str:
        definition = DatasetDefinition(
            code=GOLDEN_DATASET_CODE,
            version=code_ver,
            name=f"proc {processor_ref}",
            frequency="1d",
            universe_code=base.universe_code,
            universe_version=base.universe_version,
            snapshot_id=base.snapshot_id,
            schema_version=base.schema_version,
            features=base.features,
            price_policy=base.price_policy,
            processor=processor_ref,
            pit=True,
        )
        registry.upsert_dataset(definition, status="validated")
        return f"{GOLDEN_DATASET_CODE}@{code_ver}"

    ref_cs = _upsert("v1_cs", "cs_zscore@1")
    ref_std = _upsert("v1_std", "qd_standard@1")
    resolver = VersionResolver(query, registry)
    a = resolver.resolve(ref_cs)
    b = resolver.resolve(ref_std)
    assert a.pipeline_digest != b.pipeline_digest
    assert a.bundle_hash != b.bundle_hash
    assert a.dataset_hash != b.dataset_hash  # Domain 亦因 processor 字段变化


def test_fit_required_rejects_string_build_handler(golden_qlib_env, tmp_path):
    """含 RobustZScore 的 processor 禁止 build_handler(str)。"""
    query = golden_qlib_env["query"]
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_qd_standard_processor())
    handle = query.dataset(golden_qlib_env["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_fit",
        name="needs fit",
        frequency="1d",
        universe_code=base.universe_code,
        universe_version=base.universe_version,
        snapshot_id=base.snapshot_id,
        schema_version=base.schema_version,
        features=base.features,
        price_policy=base.price_policy,
        processor="qd_standard@1",
        pit=True,
    )
    registry.upsert_dataset(definition, status="validated")
    adapter = QlibAdapter(
        query,
        materializer=golden_qlib_env["materializer"],
        registry=registry,
        dataset_cache_root=tmp_path / "ds_cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    with pytest.raises(QlibAdapterError, match="ResearchDatasetSpec"):
        adapter.build_handler(f"{GOLDEN_DATASET_CODE}@v1_fit")


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("qlib") is None,
    reason="pyqlib required",
)
def test_qd_standard_via_spec_fetch_and_fit_window(golden_qlib_env, tmp_path):
    """ResearchDatasetSpec 路径：fit 窗 = train；fetch 非空。"""
    query = golden_qlib_env["query"]
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_qd_standard_processor())
    handle = query.dataset(golden_qlib_env["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_std_run",
        name="standard pipeline",
        frequency="1d",
        universe_code=base.universe_code,
        universe_version=base.universe_version,
        snapshot_id=base.snapshot_id,
        schema_version=base.schema_version,
        features=base.features,
        price_policy=base.price_policy,
        processor="qd_standard@1",
        pit=True,
    )
    registry.upsert_dataset(definition, status="validated")
    ref = f"{GOLDEN_DATASET_CODE}@v1_std_run"

    adapter = QlibAdapter(
        query,
        materializer=golden_qlib_env["materializer"],
        registry=registry,
        dataset_cache_root=tmp_path / "ds_cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    segments = _segments()
    spec = ResearchDatasetSpec(dataset_ref=ref, segments=segments)
    assert spec.resolved_fit_end() < segments.valid.start

    qd = adapter.build_qd_handler(spec, force_materialize=True)
    assert qd.fit_start == "2024-01-01"
    assert qd.fit_end == "2024-02-29"

    # 编译后的 learn processors：仅 RobustZScore 带 fit_*
    learn, _ = adapter._processors.build_handler_processors(qd.bundle.processor)
    injected = inject_fit_window(learn, qd.fit_start, qd.fit_end)
    for step in injected:
        if step["class"] == "RobustZScoreNorm":
            assert step["kwargs"]["fit_end_time"] == "2024-02-29"
        else:
            assert "fit_start_time" not in step.get("kwargs", {})

    feat = qd.fetch(col_set="feature")
    assert feat is not None and len(feat) > 0

    # 同 spec 二次 build → cache hit + 数值可复现
    ds1 = adapter.build_dataset(spec)
    ds2 = adapter.build_dataset(spec)
    assert ds2.qd_cache_hit is True  # type: ignore[attr-defined]
    assert ds1.qd_bundle_hash == ds2.qd_bundle_hash  # type: ignore[attr-defined]


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("qlib") is None,
    reason="pyqlib required",
)
def test_pit_no_fundamental_with_processor(golden_qlib_env, tmp_path):
    query = golden_qlib_env["query"]
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_identity_processor())
    # identity 不需 fit，仍走 spec
    adapter = QlibAdapter(
        query,
        materializer=golden_qlib_env["materializer"],
        registry=registry,
        dataset_cache_root=tmp_path / "ds_cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    # 默认 golden processor=None；PIT spy 在 handler 内
    qd = adapter.build_qd_handler(
        ResearchDatasetSpec(
            dataset_ref=golden_qlib_env["dataset_ref"],
            segments=_segments(),
        ),
        force_materialize=True,
    )
    assert qd.instruments
