"""三级比较：Input / Prediction / Artifact → ReproResult。"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .input_manifest import verify_input_manifest
from .protocol import (
    ReproResult,
    ReproducibilityInject,
    ReproducibilityManifest,
    ReproducibilityPolicy,
    SeedBundle,
    TrainingInputManifest,
)
from .seeds import seed_match


def _corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _rank(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    for r, i in enumerate(order):
        ranks[i] = float(r)
    return ranks


def compare_predictions(
    original: Sequence[Mapping[str, Any]],
    reproduced: Sequence[Mapping[str, Any]],
    *,
    tolerance: float,
) -> dict[str, Any]:
    o = [float(r.get("prediction") or 0.0) for r in original]
    p = [float(r.get("prediction") or 0.0) for r in reproduced]
    n = min(len(o), len(p))
    if n == 0:
        return {
            "mae": None,
            "rmse": None,
            "max_abs_error": None,
            "correlation": None,
            "rank_correlation": None,
            "within_tolerance": tolerance >= 0 and n == 0 and len(o) == len(p),
            "n": 0,
        }
    o, p = o[:n], p[:n]
    abs_err = [abs(a - b) for a, b in zip(o, p)]
    mae = sum(abs_err) / n
    rmse = math.sqrt(sum(e * e for e in abs_err) / n)
    max_abs = max(abs_err)
    corr = _corr(o, p)
    rank_corr = _corr(_rank(o), _rank(p))
    within = max_abs <= float(tolerance) if tolerance > 0 else max_abs == 0.0
    return {
        "mae": mae,
        "rmse": rmse,
        "max_abs_error": max_abs,
        "correlation": corr,
        "rank_correlation": rank_corr,
        "within_tolerance": within,
        "n": n,
    }


def compare_metrics(
    original: Mapping[str, Any],
    reproduced: Mapping[str, Any],
    *,
    tolerance: float,
) -> dict[str, Any]:
    keys = sorted(set(original) | set(reproduced))
    diffs: dict[str, float] = {}
    within = True
    for k in keys:
        ov, rv = original.get(k), reproduced.get(k)
        if isinstance(ov, (int, float)) and isinstance(rv, (int, float)):
            d = abs(float(ov) - float(rv))
            diffs[k] = d
            if tolerance > 0:
                if d > float(tolerance):
                    within = False
            elif d != 0.0:
                within = False
        elif ov != rv:
            within = False
            diffs[k] = float("nan")
    return {"diffs": diffs, "within_tolerance": within}


def compare_artifact_checksums(original: str, reproduced: str) -> dict[str, Any]:
    o = (original or "").strip()
    r = (reproduced or "").strip()
    return {"original": o, "reproduced": r, "match": bool(o) and o == r}


def evaluate_prechecks(
    source: ReproducibilityManifest,
    *,
    current_env_hash: str,
    current_dep_hash: str,
    current_code_commit: str,
    current_seeds: SeedBundle,
    current_input: TrainingInputManifest,
    policy: ReproducibilityPolicy,
    inject: ReproducibilityInject | None = None,
) -> tuple[ReproResult | None, dict[str, bool], str]:
    """PREPARING 校验；返回 (early_result_or_None, flags, reason)。"""
    # apply mutations from inject as "current" world
    cur_input = current_input
    env_hash = current_env_hash
    dep_hash = current_dep_hash
    code = current_code_commit
    seeds = current_seeds
    dataset_hash = source.dataset_hash
    snapshot_id = source.snapshot_id
    feature_hash = source.feature_set_hash
    processor = source.processor_version

    if inject:
        if inject.mutate_dataset_hash:
            dataset_hash = inject.mutate_dataset_hash
            cur_input = cur_input.model_copy(update={"dataset_hash": dataset_hash})
        if inject.mutate_snapshot_id:
            snapshot_id = inject.mutate_snapshot_id
            cur_input = cur_input.model_copy(update={"snapshot_id": snapshot_id})
        if inject.mutate_feature_set_hash:
            feature_hash = inject.mutate_feature_set_hash
        if inject.mutate_processor_version:
            processor = inject.mutate_processor_version
        if inject.mutate_partition_checksum and cur_input.partitions:
            parts = []
            for i, p in enumerate(cur_input.partitions):
                if i == 0:
                    parts.append(
                        p.model_copy(update={"checksum": inject.mutate_partition_checksum})
                    )
                else:
                    parts.append(p)
            from .hashing import compute_input_manifest_hash

            cur_input = cur_input.model_copy(update={"partitions": parts})
            cur_input = cur_input.model_copy(
                update={
                    "input_manifest_hash": compute_input_manifest_hash(
                        cur_input.model_dump(mode="json")
                    )
                }
            )
        if inject.mutate_code_commit:
            code = inject.mutate_code_commit
        if inject.mutate_dependency_lock_hash:
            dep_hash = inject.mutate_dependency_lock_hash
        if inject.mutate_environment_hash:
            env_hash = inject.mutate_environment_hash
        if inject.mutate_seed is not None:
            seeds = SeedBundle(
                master_seed=inject.mutate_seed,
                python_seed=inject.mutate_seed,
                numpy_seed=inject.mutate_seed,
                qlib_seed=inject.mutate_seed,
                framework_seed=inject.mutate_seed,
                model_seed=inject.mutate_seed,
            )

    input_reasons = verify_input_manifest(source.input_manifest, cur_input)
    data_mismatch = any(
        r in ("partition_checksum_mismatch", "dataset_hash_mismatch")
        for r in input_reasons
    )
    input_ok = not input_reasons
    if policy.dataset_match_required:
        if dataset_hash != source.dataset_hash:
            input_ok = False
            data_mismatch = True
        if snapshot_id != source.snapshot_id:
            input_ok = False
        if feature_hash != source.feature_set_hash:
            input_ok = False
        if processor != source.processor_version:
            input_ok = False

    code_ok = (not policy.code_match_required) or (
        code == (source.code_commit or source.code_version)
        or code == source.code_commit
    )
    # if source has code_commit, require exact; else fall back to code_version
    if policy.code_match_required and source.code_commit:
        code_ok = code == source.code_commit
    elif policy.code_match_required:
        code_ok = code == source.code_version or code == source.code_commit

    env_ok = (not policy.environment_match_required) or (
        env_hash == source.environment_hash
    )
    dep_ok = (not policy.dependency_match_required) or (
        dep_hash == source.dependency_lock_hash
    )
    seed_ok = (not policy.seed_match_required) or seed_match(source.seeds, seeds)

    flags = {
        "input_match": input_ok and not input_reasons,
        "code_match": code_ok,
        "environment_match": env_ok,
        "dependency_match": dep_ok,
        "seed_match": seed_ok,
    }

    if data_mismatch or (
        inject
        and inject.mutate_partition_checksum
        and "partition_checksum_mismatch" in input_reasons
    ):
        return "DATA_MISMATCH", flags, "; ".join(input_reasons) or "data_mismatch"
    if not flags["input_match"] or (
        snapshot_id != source.snapshot_id
        or feature_hash != source.feature_set_hash
        or processor != source.processor_version
    ):
        if policy.dataset_match_required and (
            snapshot_id != source.snapshot_id
            or feature_hash != source.feature_set_hash
            or processor != source.processor_version
            or input_reasons
        ):
            return (
                "INPUT_MISMATCH",
                flags,
                "; ".join(input_reasons)
                or "snapshot_feature_or_processor_mismatch",
            )
    if not code_ok:
        return "CODE_MISMATCH", flags, "code_commit_mismatch"
    if not dep_ok:
        return "DEPENDENCY_MISMATCH", flags, "dependency_lock_hash_mismatch"
    if not env_ok:
        return "ENV_MISMATCH", flags, "environment_hash_mismatch"
    if not seed_ok:
        return "SEED_MISMATCH", flags, "seed_bundle_mismatch"
    return None, flags, ""


def finalize_result(
    *,
    policy: ReproducibilityPolicy,
    flags: Mapping[str, bool],
    artifact_cmp: Mapping[str, Any],
    metrics_cmp: Mapping[str, Any],
    pred_cmp: Mapping[str, Any],
    source: ReproducibilityManifest,
) -> tuple[ReproResult, str]:
    if policy.mode == "AUDITABLE":
        if flags.get("input_match") and flags.get("code_match"):
            return "AUDIT_OK", "auditable_conditions_complete"
        return "REPRODUCTION_FAILED", "audit_incomplete"

    art_match = bool(artifact_cmp.get("match"))
    met_ok = bool(metrics_cmp.get("within_tolerance"))
    pred_ok = bool(pred_cmp.get("within_tolerance"))

    if (
        not source.deterministic_enabled
        or not source.deterministic_supported
    ) and not art_match:
        if policy.mode == "REPRODUCIBLE" and met_ok and pred_ok:
            return "NUMERICAL_MATCH", "non_deterministic_but_numerical_ok"
        return "NON_DETERMINISTIC", "deterministic_not_enabled"

    if policy.artifact_match_required and art_match and met_ok and pred_ok:
        return "EXACT_MATCH", "artifact_and_outputs_match"
    if policy.artifact_match_required and art_match:
        return "EXACT_MATCH", "artifact_checksum_match"

    if policy.mode == "REPRODUCIBLE" or not policy.artifact_match_required:
        if met_ok and pred_ok:
            return "NUMERICAL_MATCH", "metrics_and_predictions_within_tolerance"

    if policy.artifact_match_required and not art_match:
        return "REPRODUCTION_FAILED", "artifact_checksum_mismatch"
    return "REPRODUCTION_FAILED", "outputs_out_of_tolerance"


__all__ = [
    "compare_artifact_checksums",
    "compare_metrics",
    "compare_predictions",
    "evaluate_prechecks",
    "finalize_result",
]
