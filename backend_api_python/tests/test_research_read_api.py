"""Phase 10B/10F-1 research read routes."""

from __future__ import annotations

import json

import pytest

from app.services.research_data.contracts import (
    DatasetDefinition,
    ExperimentDefinition,
    FactorDatasetRecord,
    FactorEvaluationSummary,
    FeatureDefinition,
    GroupEvaluationSummary,
    LabelDefinition,
    PricePolicy,
)
from app.services.research_data.registry import LocalJsonRegistry


@pytest.fixture()
def registry(tmp_path):
    reg = LocalJsonRegistry(root=tmp_path / "registry")
    definition = DatasetDefinition(
        code="ds_test",
        version="v1",
        name="Test Dataset",
        frequency="1d",
        universe_code="CSI300",
        universe_version="v1",
        snapshot_id="snap_test",
        schema_version="schema@1",
        features=["close", "volume"],
        label=LabelDefinition(code="fwd_ret", version="v1", name="Forward Return", expression="ret"),
        price_policy=PricePolicy(),
        pit=True,
        processor="proc@v1",
    )
    reg.create_snapshot(
        snapshot_id="snap_test",
        name="snap",
        items=[{"dataset_code": "m", "version": "v1", "checksum": "abc"}],
    )
    reg.upsert_dataset(definition, status="READY")
    reg.upsert_experiment(
        ExperimentDefinition(
            experiment_id="exp_demo",
            name="Demo",
            dataset_ref="ds_test@v1",
            snapshot_id="snap_test",
            dataset_hash="hash",
        )
    )
    reg.upsert_feature(
        FeatureDefinition(
            code="alpha_mom",
            version="v1",
            name="Momentum",
            expression="close / delay(close, 20) - 1",
            factor_type="TECHNICAL",
            factor_hash="fhash_mom_001",
        )
    )
    return reg


@pytest.fixture()
def client(app, monkeypatch, registry):
    import app.services.research_data.research_query.service as rq_mod
    import app.services.research_data.experiment_platform.service as exp_mod

    monkeypatch.setattr(rq_mod, "_service", None)
    monkeypatch.setattr(exp_mod, "_service", None)
    monkeypatch.setattr(
        rq_mod,
        "get_research_query_service",
        lambda: rq_mod.ResearchQueryService(registry=registry),
    )
    monkeypatch.setattr(
        exp_mod,
        "get_experiment_platform_service",
        lambda: exp_mod.ExperimentPlatformService(registry=registry),
    )

    def _noop(f):
        return f

    monkeypatch.setattr("app.routes.research_read.login_required", _noop)
    return app.test_client()


def test_list_datasets(client):
    resp = client.get("/api/research/datasets")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 1
    row = next(item for item in body["data"] if item["dataset_id"] == "ds_test@v1")
    assert row["label_name"] == "Forward Return"
    assert row["pit_policy"] == "STRICT"
    assert "close" in row["feature_set"]


def test_get_dataset_detail(client):
    resp = client.get("/api/research/datasets/ds_test@v1")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["name"] == "Test Dataset"
    assert data["feature_count"] == 2
    assert data["snapshot_id"] == "snap_test"
    assert data["processor"] == "proc@v1"
    assert data["price_policy"] == "RAW"
    assert data["preview_available"] is False
    assert data["preview_rows"] == []


def test_list_experiments(client):
    resp = client.get("/api/research/experiments")
    assert resp.status_code == 200
    ids = [row["experiment_id"] for row in resp.get_json()["data"]]
    assert "exp_demo" in ids


def test_create_experiment(client):
    resp = client.post(
        "/api/research/experiments",
        data=json.dumps(
            {
                "name": "New Exp",
                "datasetRef": "ds_test@v1",
                "featureRefs": [],
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["name"] == "New Exp"
    assert data["dataset_ref"] == "ds_test@v1"


def test_alpha_factor_evaluation_empty(client):
    resp = client.get("/api/research/alpha-factors/alpha_mom@v1/evaluation")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["has_result"] is False
    assert data["series"]["dates"] == []
    assert data["mean_ic"] is None


def test_alpha_factor_evaluation_real_summary(client, registry, tmp_path):
    registry.upsert_factor_dataset(
        FactorDatasetRecord(
            factor_dataset_id="fd_mom",
            factor_ref="alpha_mom@v1",
            factor_hash="fhash_mom_001",
            dataset_hash="dhash",
            snapshot_id="snap_test",
        )
    )
    series_path = tmp_path / "ic_series.json"
    series_path.write_text(
        json.dumps(
            {
                "dates": ["2024-01-02", "2024-01-03"],
                "ic": [0.01, 0.02],
                "rank_ic": [0.015, 0.025],
            }
        ),
        encoding="utf-8",
    )
    registry.upsert_factor_evaluation_summary(
        FactorEvaluationSummary(
            metric_hash="mhash_001",
            evaluation_hash="ehash_001",
            factor_dataset_id="fd_mom",
            horizon=1,
            mean_ic=0.015,
            mean_rank_ic=0.02,
            ic_ir=1.2,
            rank_ic_ir=1.1,
            storage_uri=str(series_path),
            metadata={"factor_hash": "fhash_mom_001", "factor_ref": "alpha_mom@v1"},
        )
    )
    registry.upsert_factor_group_evaluation(
        GroupEvaluationSummary(
            group_evaluation_hash="ghash_001",
            evaluation_hash="ehash_001",
            factor_dataset_id="fd_mom",
            horizon=1,
            mean_turnover=0.12,
        )
    )

    resp = client.get("/api/research/alpha-factors/alpha_mom@v1/evaluation")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["has_result"] is True
    assert data["mean_ic"] == pytest.approx(0.015)
    assert data["ic_ir"] == pytest.approx(1.2)
    assert data["turnover"] == pytest.approx(0.12)
    assert data["evaluation_hash"] == "ehash_001"
    assert data["series"]["dates"] == ["2024-01-02", "2024-01-03"]
    assert data["series"]["ic"][0] == pytest.approx(0.01)

    detail = client.get("/api/research/alpha-factors/alpha_mom@v1").get_json()["data"]
    assert detail["expression"].startswith("close / delay")
    assert detail["icir"] == pytest.approx(1.2)


def test_product_status_semantic_empty(client):
    resp = client.get("/api/research/product-status")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["research"]["dataset"] == "DATASET_READY"
    # Feature exists but no ACTIVE model
    assert data["research"]["factor"] == "FACTOR_READY"
    assert data["research"]["model"] == "EMPTY_MODEL"
