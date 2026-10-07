"""Model / ModelVersion 内存索引。"""

from __future__ import annotations

from typing import Iterable

from .protocol import Model, ModelVersion


class ModelCatalog:
    def __init__(self) -> None:
        self._models: dict[str, Model] = {}
        self._by_code: dict[str, str] = {}
        self._versions: dict[str, ModelVersion] = {}
        self._versions_by_model: dict[str, list[str]] = {}
        self._version_ref: dict[str, str] = {}

    def upsert_model(self, model: Model) -> None:
        self._models[model.model_id] = model
        self._by_code[model.model_code] = model.model_id

    def get_model(self, model_id: str) -> Model | None:
        return self._models.get(model_id)

    def get_model_by_code(self, model_code: str) -> Model | None:
        mid = self._by_code.get(model_code)
        return self._models.get(mid) if mid else None

    def list_models(self) -> list[Model]:
        return list(self._models.values())

    def upsert_version(self, version: ModelVersion) -> None:
        self._versions[version.model_version_id] = version
        refs = self._versions_by_model.setdefault(version.model_id, [])
        if version.model_version_id not in refs:
            refs.append(version.model_version_id)
        ref = f"{version.model_code}@{version.version}"
        self._version_ref[ref] = version.model_version_id

    def get_version(self, model_version_id: str) -> ModelVersion | None:
        return self._versions.get(model_version_id)

    def get_version_by_ref(self, ref: str) -> ModelVersion | None:
        vid = self._version_ref.get(ref)
        return self._versions.get(vid) if vid else None

    def list_versions(self, model_id: str | None = None) -> list[ModelVersion]:
        if model_id is None:
            return list(self._versions.values())
        ids = self._versions_by_model.get(model_id, [])
        return [self._versions[i] for i in ids if i in self._versions]

    def load_models(self, models: Iterable[Model]) -> None:
        for m in models:
            self.upsert_model(m)

    def load_versions(self, versions: Iterable[ModelVersion]) -> None:
        for v in versions:
            self.upsert_version(v)


__all__ = ["ModelCatalog"]
