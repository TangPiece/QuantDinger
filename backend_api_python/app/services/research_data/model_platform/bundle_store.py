"""Model Artifact Bundle Store：put/get/verify/delete（不可变 AVAILABLE）。"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.services.research_data.canonical_store import CanonicalStore, LocalCanonicalStore

from .artifact_fsm import (
    ArtifactLifecycleError,
    assert_artifact_status_transition,
    is_content_sealed,
)
from .artifact_manifest import build_artifact_manifest, normalize_artifact_type
from .artifact_store import ModelArtifactStore
from .identity import new_artifact_id
from .immutability import load_json_model
from .pin import pin_model_artifact
from .protocol import ModelArtifact, ModelArtifactSpec, TrainingRun
from .writers import write_artifact


class BundleStoreError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "ARTIFACT_ERROR") -> None:
        super().__init__(message)
        self.failure_class = failure_class


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stub_payload_for_run(run: TrainingRun) -> bytes:
    """确定性 stub bin；checksum 由内容计算。"""
    payload = (
        f"QD_STUB_MODEL\n"
        f"run={run.training_run_id}\n"
        f"hash={run.training_run_hash}\n"
        f"cfg={run.training_config_hash}\n"
    )
    return payload.encode("utf-8")


class ModelBundleStore:
    """按 artifact_id 落盘 Bundle；索引写入 model_platform/artifacts。"""

    def __init__(
        self,
        platform_store: ModelArtifactStore,
        *,
        canonical: CanonicalStore | None = None,
    ) -> None:
        self._plat = platform_store
        # Canonical root 与 platform cache 对齐
        if canonical is not None:
            self._canonical = canonical
        else:
            from .artifact_store import cache_base

            self._canonical = LocalCanonicalStore(root=cache_base(platform_store.root))

    def exists(self, artifact_id: str) -> bool:
        bin_path = self._plat.bundle_dir(artifact_id=artifact_id) / "model.bin"
        return bin_path.is_file()

    def bundle_path(self, artifact_id: str) -> Path:
        return self._plat.bundle_dir(artifact_id=artifact_id)

    def get(self, artifact_id: str) -> bytes:
        path = self.bundle_path(artifact_id) / "model.bin"
        if not path.is_file():
            # try canonical
            key = f"{self._plat.bundle_key_prefix(artifact_id=artifact_id)}/model.bin"
            try:
                return self._canonical.get_bytes(key)
            except FileNotFoundError as exc:
                raise BundleStoreError(
                    f"artifact payload missing: {artifact_id}",
                    failure_class="ARTIFACT_ERROR",
                ) from exc
        return path.read_bytes()

    def metadata(self, artifact_id: str) -> dict[str, Any]:
        meta = self.bundle_path(artifact_id) / "metadata.json"
        if meta.is_file():
            return json.loads(meta.read_text(encoding="utf-8"))
        return {}

    def read_manifest(self, artifact_id: str) -> dict[str, Any]:
        man = self.bundle_path(artifact_id) / "manifest.json"
        if not man.is_file():
            raise BundleStoreError(f"manifest missing: {artifact_id}")
        return json.loads(man.read_text(encoding="utf-8"))

    def verify(self, artifact_id: str, *, expected_checksum: str = "") -> bool:
        raw = self.get(artifact_id)
        digest = sha256_bytes(raw)
        man = self.read_manifest(artifact_id)
        content = man.get("content") or {}
        expect = expected_checksum or str(content.get("checksum") or "")
        if not expect:
            raise BundleStoreError("no expected checksum for verify")
        if digest != expect:
            raise BundleStoreError(
                f"checksum mismatch: got={digest} expected={expect}",
                failure_class="ARTIFACT_ERROR",
            )
        chk_file = self.bundle_path(artifact_id) / "checksum.sha256"
        if chk_file.is_file():
            file_digest = chk_file.read_text(encoding="utf-8").strip().split()[0]
            if file_digest != digest:
                raise BundleStoreError(
                    f"checksum.sha256 mismatch: {file_digest} != {digest}",
                    failure_class="ARTIFACT_ERROR",
                )
        return True

    def put(
        self,
        payload: bytes,
        *,
        run: TrainingRun | None = None,
        model_version_id: str = "",
        model_id: str = "",
        framework: str = "",
        framework_version: str = "",
        lineage: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        artifact_id: str | None = None,
        source_uri: str = "",
    ) -> ModelArtifact:
        """CREATING→UPLOADING→VERIFYING→AVAILABLE；失败 FAILED/CORRUPTED。"""
        aid = artifact_id or new_artifact_id()
        existing_idx = load_json_model(self._plat.artifact_path(artifact_id=aid), ModelArtifact)
        if existing_idx is not None and is_content_sealed(existing_idx.status):
            raise BundleStoreError(
                f"artifact {aid} is AVAILABLE and immutable; create a new artifact_id",
                failure_class="ARTIFACT_ERROR",
            )
        if self.exists(aid) and existing_idx and is_content_sealed(existing_idx.status):
            raise BundleStoreError(
                f"refuse overwrite sealed bundle: {aid}",
                failure_class="ARTIFACT_ERROR",
            )

        digest = sha256_bytes(payload)
        size = len(payload)
        producer_type = "training_run" if run else ""
        producer_id = run.training_run_id if run else ""
        lin = dict(lineage or {})
        if run:
            lin.setdefault("dataset_hash", run.dataset_hash)
            lin.setdefault("feature_set_hash", run.feature_set_hash)
            lin.setdefault("label_hash", run.label_hash)
            lin.setdefault("processor_version", run.processor_version)
            lin.setdefault("training_config_hash", run.training_config_hash)
            lin.setdefault("snapshot_id", run.snapshot_id)

        art = pin_model_artifact(
            ModelArtifactSpec(
                model_version_id=model_version_id,
                artifact_type="MODEL",
                checksum=digest,
                checksum_algorithm="SHA256",
                file_size=size,
                framework=framework or (run.framework if run else ""),
                framework_version=framework_version
                or (run.framework_version if run else ""),
                producer_type=producer_type,
                producer_id=producer_id,
                status="CREATING",
                metadata=dict(metadata or {}),
            ),
            artifact_id=aid,
        )
        write_artifact(self._plat, art)

        try:
            art = self._transition(art, "UPLOADING")
            dest = self.bundle_path(aid)
            # 清空未密封目录
            if dest.exists() and not (existing_idx and is_content_sealed(existing_idx.status)):
                for child in dest.iterdir():
                    if child.is_file():
                        child.unlink()
            dest.mkdir(parents=True, exist_ok=True)
            bin_path = dest / "model.bin"
            bin_path.write_bytes(payload)

            # Canonical mirror
            prefix = self._plat.bundle_key_prefix(artifact_id=aid)
            self._canonical.put_bytes(f"{prefix}/model.bin", payload)

            # sidecars
            meta_obj = {
                "artifact_id": aid,
                "producer_type": producer_type,
                "producer_id": producer_id,
                "source_uri": source_uri,
                "framework": art.framework,
                "lineage": lin,
                **dict(metadata or {}),
            }
            meta_text = json.dumps(meta_obj, ensure_ascii=False, indent=2, sort_keys=True)
            (dest / "metadata.json").write_text(meta_text, encoding="utf-8")
            self._canonical.put_bytes(f"{prefix}/metadata.json", meta_text.encode("utf-8"))

            for name in (
                "feature_schema.json",
                "processor.json",
                "label_definition.json",
                "environment.json",
            ):
                empty = "{}\n"
                (dest / name).write_text(empty, encoding="utf-8")
                self._canonical.put_bytes(f"{prefix}/{name}", empty.encode("utf-8"))

            (dest / "checksum.sha256").write_text(f"{digest}  model.bin\n", encoding="utf-8")
            self._canonical.put_bytes(
                f"{prefix}/checksum.sha256",
                f"{digest}  model.bin\n".encode("utf-8"),
            )

            art = self._transition(art, "VERIFYING")
            man = build_artifact_manifest(
                artifact_id=aid,
                training_run_id=producer_id,
                model_id=model_id,
                model_version_id=model_version_id,
                framework=art.framework,
                framework_version=art.framework_version,
                checksum=digest,
                file_size=size,
                lineage=lin,
                metadata=dict(metadata or {}),
            )
            man_text = man.model_dump_json(indent=2)
            man_path = dest / "manifest.json"
            man_path.write_text(man_text, encoding="utf-8")
            self._canonical.put_bytes(f"{prefix}/manifest.json", man_text.encode("utf-8"))

            # verify
            got = sha256_bytes(bin_path.read_bytes())
            if got != digest:
                art = self._fail(art, "CORRUPTED", f"post-write checksum {got} != {digest}")
                raise BundleStoreError(
                    f"verify failed for {aid}",
                    failure_class="ARTIFACT_ERROR",
                )

            now = datetime.now(timezone.utc)
            art = art.model_copy(
                update={
                    "status": "AVAILABLE",
                    "artifact_uri": str(bin_path.resolve()),
                    "manifest_uri": str(man_path.resolve()),
                    "metadata_uri": str((dest / "metadata.json").resolve()),
                    "feature_schema_uri": str((dest / "feature_schema.json").resolve()),
                    "processor_uri": str((dest / "processor.json").resolve()),
                    "label_definition_uri": str((dest / "label_definition.json").resolve()),
                    "environment_uri": str((dest / "environment.json").resolve()),
                    "immutable_at": now,
                    "checksum": digest,
                    "file_size": size,
                    "artifact_type": normalize_artifact_type("MODEL"),
                }
            )
            assert_artifact_status_transition("VERIFYING", "AVAILABLE")
            write_artifact(self._plat, art)
            return art
        except BundleStoreError:
            raise
        except Exception as exc:
            self._fail(art, "FAILED", str(exc))
            raise BundleStoreError(str(exc), failure_class="ARTIFACT_ERROR") from exc

    def _transition(self, art: ModelArtifact, target: str) -> ModelArtifact:
        assert_artifact_status_transition(art.status, target)  # type: ignore[arg-type]
        updated = art.model_copy(update={"status": target})
        write_artifact(self._plat, updated)
        return updated

    def _fail(self, art: ModelArtifact, status: str, reason: str) -> ModelArtifact:
        try:
            assert_artifact_status_transition(art.status, status)  # type: ignore[arg-type]
        except ArtifactLifecycleError:
            # force terminal from VERIFYING/UPLOADING already allowed
            pass
        meta = dict(art.metadata or {})
        meta["failure_reason"] = reason
        updated = art.model_copy(update={"status": status, "metadata": meta})
        write_artifact(self._plat, updated)
        return updated

    def delete(
        self,
        artifact_id: str,
        *,
        referenced_by_versions: list[str] | None = None,
    ) -> None:
        refs = list(referenced_by_versions or [])
        if refs:
            raise BundleStoreError(
                f"delete forbidden: artifact {artifact_id} referenced by {refs}",
                failure_class="ARTIFACT_ERROR",
            )
        art = load_json_model(self._plat.artifact_path(artifact_id=artifact_id), ModelArtifact)
        if art is not None and art.status == "AVAILABLE" and art.model_version_id:
            raise BundleStoreError(
                f"delete forbidden: artifact {artifact_id} bound to {art.model_version_id}",
                failure_class="ARTIFACT_ERROR",
            )
        dest = self.bundle_path(artifact_id)
        if dest.is_dir():
            shutil.rmtree(dest)
        idx = self._plat.artifact_path(artifact_id=artifact_id)
        if idx.is_file():
            idx.unlink()


__all__ = [
    "BundleStoreError",
    "ModelBundleStore",
    "sha256_bytes",
    "stub_payload_for_run",
]
