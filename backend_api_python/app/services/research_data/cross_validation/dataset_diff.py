"""L1 Dataset Diff。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import LayerResult


def diff_dataset(
    qd_id: Mapping[str, Any],
    qlib_id: Mapping[str, Any],
    *,
    bar_summary: Mapping[str, Any] | None = None,
) -> LayerResult:
    """比较 dataset / materialization 身份；注入 bars 时检查质量。"""
    details: dict[str, Any] = {"qd": dict(qd_id), "qlib": dict(qlib_id)}
    mismatches: list[str] = []

    # materialization / dataset_hash 优先；注入场景允许 metadata 钉住
    qd_mat = str(qd_id.get("materialization_id") or "")
    ql_mat = str(qlib_id.get("materialization_id") or "")
    if qd_mat and ql_mat and qd_mat != ql_mat:
        mismatches.append(f"materialization_id {qd_mat}!={ql_mat}")

    qd_dh = str(qd_id.get("dataset_hash") or "")
    ql_dh = str(qlib_id.get("dataset_hash") or "")
    if qd_dh and ql_dh and qd_dh != ql_dh:
        mismatches.append(f"dataset_hash {qd_dh}!={ql_dh}")

    # 无 materialization 时：factor_dataset_id / dataset_ref 对齐
    if not qd_mat and not ql_mat:
        qd_ref = str(qd_id.get("dataset_ref") or qd_id.get("factor_dataset_id") or "")
        ql_ref = str(qlib_id.get("dataset_ref") or qlib_id.get("factor_dataset_id") or "")
        if qd_ref and ql_ref and qd_ref != ql_ref:
            mismatches.append(f"dataset_ref {qd_ref}!={ql_ref}")

    if bar_summary:
        details["bars"] = dict(bar_summary)
        if bar_summary.get("has_nan") or bar_summary.get("has_inf"):
            mismatches.append("bars contain NaN/Inf")
        if int(bar_summary.get("n_rows") or 0) <= 0:
            mismatches.append("empty bars")

    if mismatches:
        return LayerResult(
            layer="dataset",
            kind="EXACT",
            status="FAIL",
            message="; ".join(mismatches),
            details=details,
        )
    return LayerResult(
        layer="dataset",
        kind="EXACT",
        status="PASS",
        message="dataset identity aligned",
        details=details,
    )
