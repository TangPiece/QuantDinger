"""Phase 10B/10B-R: Research read API; Experiment write frozen until SSOT Run exists."""

from __future__ import annotations

from flask import jsonify

from app.openapi.blueprint import HumanBlueprint as Blueprint
from app.services.research_data.experiment_platform.service import (
    ExperimentPlatformError,
    get_experiment_platform_service,
)
from app.services.research_data.research_query.service import (
    ResearchQueryError,
    get_research_query_service,
)
from app.utils.auth import login_required
from app.utils.logger import get_logger

logger = get_logger(__name__)
research_blp = Blueprint("research_read", __name__)


def _ok(data, *, msg: str = "success"):
    return jsonify({"code": 1, "msg": msg, "data": data})


def _err(msg: str, status: int = 400):
    return jsonify({"code": 0, "msg": msg, "data": None}), status


@research_blp.route("/product-status", methods=["GET"])
@login_required
def research_product_status():
    svc = get_research_query_service()
    return _ok(svc.product_status().model_dump(mode="json"))


@research_blp.route("/datasets", methods=["GET"])
@login_required
def list_datasets():
    items = get_research_query_service().list_datasets()
    return _ok([i.model_dump(mode="json") for i in items])


@research_blp.route("/datasets/<path:dataset_id>", methods=["GET"])
@login_required
def get_dataset(dataset_id: str):
    try:
        item = get_research_query_service().get_dataset(dataset_id)
    except ResearchQueryError as exc:
        return _err(str(exc), 404)
    return _ok(item.model_dump(mode="json"))


@research_blp.route("/features", methods=["GET"])
@login_required
def list_features():
    items = get_research_query_service().list_features()
    return _ok([i.model_dump(mode="json") for i in items])


@research_blp.route("/features/<path:feature_id>", methods=["GET"])
@login_required
def get_feature(feature_id: str):
    try:
        item = get_research_query_service().get_feature(feature_id)
    except ResearchQueryError as exc:
        return _err(str(exc), 404)
    return _ok(item.model_dump(mode="json"))


@research_blp.route("/alpha-factors", methods=["GET"])
@login_required
def list_alpha_factors():
    items = get_research_query_service().list_alpha_factors()
    return _ok([i.model_dump(mode="json") for i in items])


@research_blp.route("/alpha-factors/<path:factor_id>", methods=["GET"])
@login_required
def get_alpha_factor(factor_id: str):
    try:
        item = get_research_query_service().get_alpha_factor(factor_id)
    except ResearchQueryError as exc:
        return _err(str(exc), 404)
    return _ok(item.model_dump(mode="json"))


@research_blp.route("/alpha-factors/<path:factor_id>/evaluation", methods=["GET"])
@login_required
def get_alpha_factor_evaluation(factor_id: str):
    try:
        item = get_research_query_service().get_alpha_factor_evaluation(factor_id)
    except ResearchQueryError as exc:
        return _err(str(exc), 404)
    return _ok(item.model_dump(mode="json"))


@research_blp.route("/factor-library", methods=["GET"])
@login_required
def list_factor_library():
    items = get_research_query_service().list_factor_library()
    return _ok([i.model_dump(mode="json") for i in items])


@research_blp.route("/factor-portfolios", methods=["GET"])
@login_required
def list_factor_portfolios():
    items = get_research_query_service().list_factor_portfolios()
    return _ok([i.model_dump(mode="json") for i in items])


@research_blp.route("/models", methods=["GET"])
@login_required
def list_models():
    items = get_research_query_service().list_models()
    return _ok([i.model_dump(mode="json") for i in items])


@research_blp.route("/models/<path:model_id>", methods=["GET"])
@login_required
def get_model(model_id: str):
    try:
        item = get_research_query_service().get_model(model_id)
    except ResearchQueryError as exc:
        return _err(str(exc), 404)
    return _ok(item.model_dump(mode="json"))


@research_blp.route("/models/<path:model_id>/lineage", methods=["GET"])
@login_required
def get_model_lineage(model_id: str):
    try:
        data = get_research_query_service().get_model_lineage(model_id)
    except ResearchQueryError as exc:
        return _err(str(exc), 404)
    return _ok(data)


@research_blp.route("/models/<path:model_id>/evaluation", methods=["GET"])
@login_required
def get_model_evaluation(model_id: str):
    try:
        data = get_research_query_service().get_model_evaluation(model_id)
    except ResearchQueryError as exc:
        return _err(str(exc), 404)
    return _ok(data)


@research_blp.route("/artifacts/<artifact_id>", methods=["GET"])
@login_required
def get_artifact(artifact_id: str):
    try:
        item = get_research_query_service().get_artifact(artifact_id)
    except ResearchQueryError as exc:
        return _err(str(exc), 404)
    return _ok(item.model_dump(mode="json"))


@research_blp.route("/experiments", methods=["GET"])
@login_required
def list_experiments():
    items = get_experiment_platform_service().list_experiments()
    return _ok([i.model_dump(mode="json") for i in items])


@research_blp.route("/experiments/<experiment_id>", methods=["GET"])
@login_required
def get_experiment(experiment_id: str):
    try:
        item = get_experiment_platform_service().get_experiment(experiment_id)
    except ExperimentPlatformError as exc:
        return _err(str(exc), 404)
    return _ok(item.model_dump(mode="json"))


@research_blp.route("/experiments", methods=["POST"])
@login_required
def create_experiment():
    """Frozen in 10B-R: register-only POST was writing status=COMPLETED without a real ExperimentRun.

    Keep GET list/detail. Re-enable write only when Experiment SSOT (Run/Job/Artifact) exists.
    """
    return _err("experiment.writeFrozen", 409)
