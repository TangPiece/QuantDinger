"""TrainingRun PREPARING 血缘门控。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import TrainingRun


class PrepareGateError(ValueError):
    def __init__(self, failure_class: str, reason: str) -> None:
        super().__init__(reason)
        self.failure_class = failure_class
        self.reason = reason


def evaluate_prepare_gate(
    run: TrainingRun,
    *,
    known_hashes: Mapping[str, str] | None = None,
    require_dataset_ref: bool = False,
    data_query: Any | None = None,
    skip_dataset_ref_check: bool = False,
) -> list[str]:
    """返回 reasons；空 = PASS。"""
    reasons: list[str] = []
    known = dict(known_hashes or {})

    if not (run.dataset_hash or "").strip():
        reasons.append("dataset_hash_missing")
    if not (run.feature_set_hash or "").strip():
        reasons.append("feature_set_hash_missing")
    if not (run.snapshot_id or "").strip():
        reasons.append("snapshot_id_missing")
    if not (run.label_hash or "").strip():
        reasons.append("label_hash_missing")
    if not (run.processor_version or "").strip():
        reasons.append("processor_version_missing")

    if require_dataset_ref and not (run.dataset_ref or "").strip():
        reasons.append("dataset_ref_missing")

    if (
        not skip_dataset_ref_check
        and data_query is not None
        and (run.dataset_ref or "").strip()
        and (run.dataset_hash or "").strip()
    ):
        try:
            handle = data_query.dataset(run.dataset_ref)
            resolved = getattr(handle, "dataset_hash", "") or ""
            if resolved and resolved != run.dataset_hash:
                reasons.append("dataset_hash_not_found")
        except Exception:
            reasons.append("dataset_hash_not_found")

    if known:
        checks = (
            ("dataset_hash", "DATA_MISSING"),
            ("feature_set_hash", "FEATURE_ERROR"),
            ("label_hash", "LABEL_ERROR"),
            ("snapshot_id", "DATA_MISSING"),
        )
        for field, _cls in checks:
            expected = known.get(field)
            actual = getattr(run, field, "")
            if expected and actual and expected != actual:
                reasons.append(f"{field}_not_found")
            if expected and not actual:
                reasons.append(f"{field}_missing")

    return reasons


def assert_prepare_pass(reasons: list[str]) -> None:
    if not reasons:
        return
    joined = "; ".join(reasons)
    if any("not_found" in r or "missing" in r for r in reasons):
        if any("feature" in r for r in reasons):
            raise PrepareGateError("FEATURE_ERROR", joined)
        if any("label" in r for r in reasons):
            raise PrepareGateError("LABEL_ERROR", joined)
        if any("dataset_ref" in r for r in reasons):
            raise PrepareGateError("CONFIG_ERROR", joined)
        raise PrepareGateError("DATA_MISSING", joined)
    raise PrepareGateError("DATA_ERROR", joined)


__all__ = [
    "PrepareGateError",
    "assert_prepare_pass",
    "evaluate_prepare_gate",
]
