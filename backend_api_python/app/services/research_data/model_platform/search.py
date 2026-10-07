"""ModelSearchQuery 过滤。"""

from __future__ import annotations

from .protocol import Model, ModelSearchQuery, ModelVersion


def model_matches(model: Model, query: ModelSearchQuery) -> bool:
    if query.model_code_prefix and not model.model_code.startswith(query.model_code_prefix):
        return False
    if query.model_type and model.model_type not in query.model_type:
        return False
    if query.framework and model.framework.upper() != query.framework.upper():
        return False
    tags = set(model.tags or [])
    if query.tags_all and not all(t in tags for t in query.tags_all):
        return False
    if query.tags_any and not any(t in tags for t in query.tags_any):
        return False
    if query.text:
        blob = " ".join(
            [model.model_code, model.name, model.description, " ".join(model.tags)]
        ).lower()
        if query.text.lower() not in blob:
            return False
    return True


def version_matches(version: ModelVersion, query: ModelSearchQuery) -> bool:
    if query.lifecycle and version.lifecycle not in query.lifecycle:
        return False
    if query.model_code_prefix and not version.model_code.startswith(query.model_code_prefix):
        return False
    if query.framework and version.framework.upper() != query.framework.upper():
        return False
    tags = set(version.tags or [])
    if query.tags_all and not all(t in tags for t in query.tags_all):
        return False
    if query.tags_any and not any(t in tags for t in query.tags_any):
        return False
    if query.text:
        blob = " ".join(
            [version.model_code, version.version, version.model_version_id, " ".join(version.tags)]
        ).lower()
        if query.text.lower() not in blob:
            return False
    return True


def search_models(models: list[Model], query: ModelSearchQuery) -> list[Model]:
    return [m for m in models if model_matches(m, query)]


def search_versions(versions: list[ModelVersion], query: ModelSearchQuery) -> list[ModelVersion]:
    return [v for v in versions if version_matches(v, query)]


__all__ = [
    "model_matches",
    "search_models",
    "search_versions",
    "version_matches",
]
