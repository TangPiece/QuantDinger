"""Forward / backward lineage helpers for Phase 8 E2E artifacts."""

from __future__ import annotations

from typing import Any


def forward_lineage_chain(artifacts: dict[str, Any]) -> list[tuple[str, str]]:
    """Promotion → baseline → monitor → guardrail → feedback → experiment."""
    chain: list[tuple[str, str]] = []
    if artifacts.get("pipeline_run_id"):
        chain.append(("promotion_run", str(artifacts["pipeline_run_id"])))
    if artifacts.get("baseline_id"):
        chain.append(("baseline", str(artifacts["baseline_id"])))
    if artifacts.get("comparison_run_id"):
        chain.append(("comparison_run", str(artifacts["comparison_run_id"])))
    if artifacts.get("alert_id"):
        chain.append(("alert", str(artifacts["alert_id"])))
    if artifacts.get("incident_id"):
        chain.append(("incident", str(artifacts["incident_id"])))
    if artifacts.get("dataset_id"):
        chain.append(("feedback_dataset", str(artifacts["dataset_id"])))
    if artifacts.get("snapshot_id"):
        chain.append(("reality_snapshot", str(artifacts["snapshot_id"])))
    if artifacts.get("case_id"):
        chain.append(("failure_case", str(artifacts["case_id"])))
    if artifacts.get("hypothesis_id"):
        chain.append(("hypothesis", str(artifacts["hypothesis_id"])))
    if artifacts.get("experiment_link_id"):
        chain.append(("experiment_link", str(artifacts["experiment_link_id"])))
    return chain


def resolve_failure_case_back(
    *,
    case: Any,
    registry: Any,
    strategy_code: str,
) -> dict[str, str]:
    """From FailureCase back to strategy / version / incident / dataset."""
    out: dict[str, str] = {
        "strategy_code": str(strategy_code),
        "case_id": str(getattr(case, "case_id", "") or ""),
        "incident_id": str(getattr(case, "incident_id", "") or ""),
        "feedback_dataset_id": str(getattr(case, "feedback_dataset_id", "") or ""),
    }
    lineage = getattr(case, "lineage", None)
    if lineage is not None:
        out["strategy_version"] = str(getattr(lineage, "strategy_version", "") or "")
        out["comparison_run_id"] = str(getattr(lineage, "comparison_run_id", "") or "")
    if out["feedback_dataset_id"]:
        try:
            ds = registry.get_production_feedback_dataset(out["feedback_dataset_id"])
            out["dataset_hash"] = str(getattr(ds, "dataset_hash", "") or "")
        except KeyError:
            pass
    return out


def assert_experiment_parent_lineage(link_row: Any, *, dataset_id: str, case_ids: list[str]) -> None:
    assert str(link_row.parent_feedback_dataset_id) == str(dataset_id)
    stored_cases = list(link_row.parent_failure_case_ids_json or [])
    for cid in case_ids:
        assert cid in stored_cases


__all__ = [
    "assert_experiment_parent_lineage",
    "forward_lineage_chain",
    "resolve_failure_case_back",
]
