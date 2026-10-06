"""Bundle Integrity：checksum / compatibility。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .protocol import ENGINE_VERSION, GateResult, ProductionBundleSummary


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_bundle_integrity(
    summary: ProductionBundleSummary,
    *,
    file_checksums: Mapping[str, str] | None = None,
) -> GateResult:
    """检查 storage 存在、manifest checksum、引擎版本。"""
    details: dict[str, Any] = {
        "bundle_hash": summary.bundle_hash,
        "engine_version": summary.engine_version,
    }
    if summary.engine_version and summary.engine_version != ENGINE_VERSION:
        # 允许同主版本前缀；完全不同则 P0
        if not str(summary.engine_version).startswith("qd_production_bridge@"):
            return GateResult(
                gate="integrity",
                passed=False,
                severity="P0",
                message=f"incompatible engine_version={summary.engine_version}",
                details=details,
            )
    uri = summary.storage_uri or ""
    if not uri:
        return GateResult(
            gate="integrity",
            passed=False,
            severity="P0",
            message="missing storage_uri",
            details=details,
        )
    root = Path(uri)
    if not root.is_dir():
        return GateResult(
            gate="integrity",
            passed=False,
            severity="P0",
            message="storage_uri not found",
            details=details,
        )
    man = root / "manifest.json"
    if not man.is_file():
        return GateResult(
            gate="integrity",
            passed=False,
            severity="P0",
            message="manifest.json missing",
            details=details,
        )
    # 校验 checksums.json（若存在）
    cpath = root / "checksums.json"
    if cpath.is_file() and file_checksums is None:
        try:
            file_checksums = json.loads(cpath.read_text(encoding="utf-8"))
        except Exception:
            file_checksums = {}
    mismatches: list[str] = []
    if file_checksums:
        for rel, expect in file_checksums.items():
            fp = root / rel
            if not fp.is_file():
                mismatches.append(f"missing:{rel}")
                continue
            got = sha256_file(fp) if fp.suffix != ".json" else sha256_text(
                fp.read_text(encoding="utf-8")
            )
            # json 用 text hash；与写入时一致
            if fp.suffix == ".json":
                got = sha256_text(fp.read_text(encoding="utf-8"))
            else:
                got = sha256_file(fp)
            if got != expect:
                mismatches.append(f"checksum:{rel}")
        details["checksum_mismatches"] = mismatches
    if mismatches:
        return GateResult(
            gate="integrity",
            passed=False,
            severity="P0",
            message="checksum mismatch",
            details=details,
        )
    if summary.checksum:
        details["summary_checksum"] = summary.checksum
    return GateResult(
        gate="integrity",
        passed=True,
        message="integrity ok",
        details=details,
    )


def assert_mutable(summary: ProductionBundleSummary) -> None:
    """APPROVED 后禁止改写 artifact。"""
    from .state_machine import StateTransitionError, is_immutable

    if is_immutable(summary.status):
        raise StateTransitionError(
            f"bundle {summary.bundle_hash} status={summary.status} is immutable"
        )
