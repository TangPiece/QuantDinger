"""ModelArtifactLoader：Version → verify → local cache → payload。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .artifact_store import ModelArtifactStore
from .bundle_store import BundleStoreError, ModelBundleStore, sha256_bytes
from .protocol import ModelArtifact, ModelVersion


class ModelLoadError(RuntimeError):
    pass


@dataclass
class LoadedModelArtifact:
    artifact_id: str
    model_version_id: str
    bin_path: Path
    checksum: str
    from_cache: bool = False


class ModelArtifactLoader:
    def __init__(
        self,
        platform_store: ModelArtifactStore,
        bundle_store: ModelBundleStore,
    ) -> None:
        self._plat = platform_store
        self._bundles = bundle_store

    def load(
        self,
        version: ModelVersion,
        artifact: ModelArtifact,
    ) -> LoadedModelArtifact:
        if not artifact.artifact_id:
            raise ModelLoadError("artifact_id missing")
        if artifact.status == "CORRUPTED":
            raise ModelLoadError(f"artifact corrupted: {artifact.artifact_id}")
        if artifact.status not in ("AVAILABLE",):
            raise ModelLoadError(
                f"artifact not AVAILABLE: {artifact.artifact_id} status={artifact.status}"
            )
        if version.artifact_id and version.artifact_id != artifact.artifact_id:
            raise ModelLoadError("version.artifact_id mismatch")

        expect = artifact.checksum
        cache = self._plat.cache_dir(artifact_id=artifact.artifact_id)
        cache_bin = cache / "model.bin"
        cache_man = cache / "manifest.json"

        if cache_bin.is_file():
            digest = sha256_bytes(cache_bin.read_bytes())
            if digest == expect:
                return LoadedModelArtifact(
                    artifact_id=artifact.artifact_id,
                    model_version_id=version.model_version_id,
                    bin_path=cache_bin.resolve(),
                    checksum=digest,
                    from_cache=True,
                )
            # mismatch → purge
            shutil.rmtree(cache, ignore_errors=True)
            cache.mkdir(parents=True, exist_ok=True)

        try:
            self._bundles.verify(artifact.artifact_id, expected_checksum=expect)
        except BundleStoreError as exc:
            raise ModelLoadError(str(exc)) from exc

        raw = self._bundles.get(artifact.artifact_id)
        digest = sha256_bytes(raw)
        if digest != expect:
            raise ModelLoadError(
                f"checksum mismatch on load: {digest} != {expect}"
            )
        cache_bin.write_bytes(raw)
        src_man = self._bundles.bundle_path(artifact.artifact_id) / "manifest.json"
        if src_man.is_file():
            cache_man.write_bytes(src_man.read_bytes())
        return LoadedModelArtifact(
            artifact_id=artifact.artifact_id,
            model_version_id=version.model_version_id,
            bin_path=cache_bin.resolve(),
            checksum=digest,
            from_cache=False,
        )


__all__ = ["LoadedModelArtifact", "ModelArtifactLoader", "ModelLoadError"]
