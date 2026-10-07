"""Phase 9E — Factor Library Platform。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.factor_library_platform.protocol import (
    ENGINE_VERSION,
    FactorSearchQuery,
)
from app.services.research_data.factor_library_platform.runner import (
    FactorLibraryError,
    FactorLibraryService,
)
from app.services.research_data.factor_library_platform.lifecycle import LibraryLifecycleError
from evaluation_platform_golden.golden import (
    GOLDEN_DATASET_REF,
    GOLDEN_FACTOR_REF,
    evaluation_inject,
)
from factor_library_platform_golden.golden import (
    GOLDEN_FACTOR_REF_B,
    library_inject,
    make_factor_library_env,
    run_golden_evaluation,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_factor_library_platform@1"


def test_no_forbidden_apis():
    assert not hasattr(FactorLibraryService, "auto_live")
    assert not hasattr(FactorLibraryService, "optimize_mv")
    assert not hasattr(FactorLibraryService, "promote_strategy")


def test_gate_failure_blocks_promotion(tmp_path: Path):
    lib, eval_svc, _ds, _reg, _days, window = make_factor_library_env(tmp_path / "gate")
    run = eval_svc.run_evaluation(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        window=window,
        inject=evaluation_inject(gate_blocked=True),
    )
    with pytest.raises(FactorLibraryError):
        lib.promote_to_library(
            factor_ref=GOLDEN_FACTOR_REF,
            evaluation_id=run.evaluation_id,
        )


def test_promotion_activate_search(tmp_path: Path):
    lib, eval_svc, _ds, _reg, days, window = make_factor_library_env(tmp_path / "promo")
    run = run_golden_evaluation(eval_svc, window, days)
    entry = lib.promote_to_library(
        factor_ref=GOLDEN_FACTOR_REF,
        evaluation_id=run.evaluation_id,
        category="MOMENTUM",
        tags=["golden", "phase9e"],
    )
    assert entry.lifecycle == "APPROVED"
    assert entry.evaluation_id == run.evaluation_id
    assert len(entry.factor_hash) == 64
    active = lib.activate(entry.entry_id)
    assert active.lifecycle == "ACTIVE"
    hits = lib.search(
        FactorSearchQuery(lifecycle=["ACTIVE"], tags_all=["golden"], category=["MOMENTUM"])
    )
    assert any(h.entry_id == entry.entry_id for h in hits)


def test_collection_portfolio_weights(tmp_path: Path):
    lib, _eval_svc, _ds, _reg, _days, _window = make_factor_library_env(tmp_path / "port")
    refs = [GOLDEN_FACTOR_REF, GOLDEN_FACTOR_REF_B]
    coll = lib.create_collection(refs, name="golden_pair")
    assert coll.collection_id
    assert set(coll.member_refs) == set(refs)
    inj = library_inject(
        weight_metrics={
            GOLDEN_FACTOR_REF: {"icir": 0.2, "volatility": 0.1},
            GOLDEN_FACTOR_REF_B: {"icir": 0.1, "volatility": 0.2},
        },
        cluster_corr_matrix={
            GOLDEN_FACTOR_REF: {GOLDEN_FACTOR_REF: 1.0, GOLDEN_FACTOR_REF_B: 0.9},
            GOLDEN_FACTOR_REF_B: {GOLDEN_FACTOR_REF: 0.9, GOLDEN_FACTOR_REF_B: 1.0},
        },
    )
    for method in ("EQUAL", "ICIR", "RISK", "CORR_ADJUSTED"):
        spec = lib.create_portfolio_spec(
            collection_id=coll.collection_id,
            weight_method=method,  # type: ignore[arg-type]
            inject=inj,
        )
        w = lib.resolve_weights(spec.portfolio_id, inject=inj)
        assert len(w) == 2
        assert abs(sum(w.values()) - 1.0) < 1e-6


def test_cluster_and_similarity(tmp_path: Path):
    lib, _, _, _, _, _ = make_factor_library_env(tmp_path / "clu")
    refs = [GOLDEN_FACTOR_REF, GOLDEN_FACTOR_REF_B]
    inj = library_inject(
        cluster_corr_matrix={
            GOLDEN_FACTOR_REF: {GOLDEN_FACTOR_REF: 1.0, GOLDEN_FACTOR_REF_B: 0.95},
            GOLDEN_FACTOR_REF_B: {GOLDEN_FACTOR_REF: 0.95, GOLDEN_FACTOR_REF_B: 1.0},
        },
    )
    cluster = lib.build_cluster(refs, inject=inj)
    assert cluster.cluster_hash
    assert len(cluster.clusters) >= 1
    sim = lib.similar_factors(GOLDEN_FACTOR_REF, top_k=5, inject=inj)
    assert sim and sim[0].factor_ref == GOLDEN_FACTOR_REF_B


def test_retired_blocks_reactivate(tmp_path: Path):
    lib, eval_svc, _ds, _reg, days, window = make_factor_library_env(tmp_path / "ret")
    run = run_golden_evaluation(eval_svc, window, days)
    entry = lib.promote_to_library(
        factor_ref=GOLDEN_FACTOR_REF,
        evaluation_id=run.evaluation_id,
    )
    lib.activate(entry.entry_id)
    lib.retire(entry.entry_id)
    with pytest.raises(LibraryLifecycleError):
        lib.activate(entry.entry_id)
    still = lib.get_entry(entry.entry_id)
    assert still.lifecycle == "RETIRED"


def test_to_feature_set(tmp_path: Path):
    lib, _, _, _, _, _ = make_factor_library_env(tmp_path / "fs")
    coll = lib.create_collection([GOLDEN_FACTOR_REF], name="solo")
    fs = lib.to_feature_set(collection_id=coll.collection_id, code="lib_fs", version="1.0.0")
    assert GOLDEN_FACTOR_REF in fs.member_refs
