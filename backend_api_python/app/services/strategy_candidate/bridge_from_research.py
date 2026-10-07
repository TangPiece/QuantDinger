"""Phase 8B：从 Experiment / Backtest / StrategyResearch 组装 Candidate lineage。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry
from app.services.strategy_registry.identity import normalize_strategy_code

from .identity import build_candidate_id, normalize_candidate_version
from .pin import content_hash_for_candidate_lineage
from .protocol import CandidateSource, StrategyCandidateRecord


class ResearchEvidenceError(ValueError):
    """研究证据缺失或 strategy_hash 不一致。"""


def _feature_version_from_experiment(exp: Any) -> str:
    refs = list(getattr(exp, "feature_refs", None) or [])
    return refs[0] if refs else ""


def _processor_from_experiment(exp: Any) -> tuple[str, str]:
    pref = str(getattr(exp, "processor_ref", None) or "").strip()
    if not pref:
        return "", ""
    if "@" in pref:
        code, ver = pref.split("@", 1)
        return ver, pref
    return pref, pref


def _model_version_from_experiment(exp: Any) -> str:
    ref = str(getattr(exp, "model_version_ref", None) or "").strip()
    if ref and "@" in ref:
        return ref.split("@", 1)[1]
    return ref


def build_candidate_from_research(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    candidate_version: str,
    experiment_id: str = "",
    backtest_hash: str = "",
    strategy_hash: str = "",
    evaluation_hash: str = "",
    cv_hash: str = "",
    risk_policy_ref: str = "",
    execution_policy_ref: str = "NEXT_OPEN",
    strategy_definition_json: Mapping[str, Any] | None = None,
    source: CandidateSource = "RESEARCH",
    model_version: str = "",
    model_artifact_id: str = "",
    dataset_hash: str = "",
    snapshot_id: str = "",
    feature_version: str = "",
    processor_version: str = "",
    processor_hash: str = "",
    metadata: Mapping[str, Any] | None = None,
    created_at: str = "",
) -> StrategyCandidateRecord:
    """从 Registry 证据链填充 lineage；显式参数优先于索引 lookup。"""
    code = normalize_strategy_code(strategy_code)
    ver = normalize_candidate_version(candidate_version)
    exp = None
    bt = None
    sr = None

    if experiment_id:
        try:
            exp = registry.get_experiment(str(experiment_id).strip())
        except Exception as exc:
            raise ResearchEvidenceError(f"experiment missing: {experiment_id}") from exc

    if backtest_hash:
        try:
            bt = registry.get_research_backtest(str(backtest_hash).strip())
        except Exception as exc:
            raise ResearchEvidenceError(f"backtest missing: {backtest_hash}") from exc

    sh = str(strategy_hash or "").strip()
    if not sh and bt is not None:
        sh = str(bt.strategy_hash or "").strip()
    if not sh and exp is not None and getattr(exp, "strategy_version", None):
        sh = str(exp.strategy_version or "").strip()
    if sh:
        try:
            sr = registry.get_strategy_research(sh)
        except Exception:
            sr = None

    if bt is not None and sh and bt.strategy_hash != sh:
        raise ResearchEvidenceError("backtest strategy_hash mismatch")
    if sr is not None and sh and sr.strategy_hash != sh:
        raise ResearchEvidenceError("strategy_research strategy_hash mismatch")

    dh = str(dataset_hash or "").strip()
    if not dh and exp is not None:
        dh = str(exp.dataset_hash or "")
    snap = snapshot_id or (exp.snapshot_id if exp else "") or (sr.snapshot_id if sr else "")

    mv = model_version or _model_version_from_experiment(exp) if exp else model_version
    if not mv and sr is not None:
        mv = str((sr.metadata or {}).get("model_version") or "")

    maid = model_artifact_id or (str(exp.model_artifact_id or "") if exp else model_artifact_id)
    fv = feature_version or (_feature_version_from_experiment(exp) if exp else feature_version)
    pv, ph = processor_version, processor_hash
    if exp is not None and not pv:
        pv, ph = _processor_from_experiment(exp)

    strat_def = dict(strategy_definition_json or {})
    if not strat_def and sr is not None:
        strat_def = {
            "signal_definition_json": dict(sr.signal_definition_json or {}),
            "rebalance_rule_json": dict(sr.rebalance_rule_json or {}),
            "holding_rule_json": dict(sr.holding_rule_json or {}),
        }

    if not risk_policy_ref and bt is not None:
        risk_policy_ref = str((bt.metadata or {}).get("risk_policy_ref") or "")
    exec_ref = execution_policy_ref or (bt.execution_policy if bt else "NEXT_OPEN")

    eval_h = evaluation_hash or (sr.evaluation_hash if sr else "")
    cv_h = cv_hash or str((bt.metadata or {}).get("cv_hash") or "") if bt else cv_hash

    content_hash = content_hash_for_candidate_lineage(
        candidate_version=ver,
        experiment_id=str(experiment_id or (exp.experiment_id if exp else "")),
        backtest_hash=str(backtest_hash or (bt.backtest_hash if bt else "")),
        model_version=mv,
        model_artifact_id=maid,
        dataset_hash=dh,
        snapshot_id=snap,
        feature_version=fv,
        processor_version=pv,
        processor_hash=ph,
        strategy_hash=sh,
        strategy_definition_json=strat_def,
        risk_policy_ref=risk_policy_ref,
        execution_policy_ref=exec_ref,
        evaluation_hash=eval_h,
        cv_hash=cv_h,
    )
    candidate_id = build_candidate_id(code, ver, content_hash)

    return StrategyCandidateRecord(
        candidate_id=candidate_id,
        strategy_code=code,
        candidate_version=ver,
        experiment_id=str(experiment_id or (exp.experiment_id if exp else "")),
        backtest_hash=str(backtest_hash or (bt.backtest_hash if bt else "")),
        model_version=mv,
        model_artifact_id=maid,
        dataset_hash=dh,
        snapshot_id=snap,
        feature_version=fv,
        processor_version=pv,
        processor_hash=ph,
        strategy_hash=sh,
        strategy_definition_json=strat_def,
        risk_policy_ref=risk_policy_ref,
        execution_policy_ref=exec_ref,
        evaluation_hash=eval_h,
        cv_hash=cv_h,
        content_hash=content_hash,
        source=source,
        status="DRAFT",
        created_at=created_at,
        metadata=dict(metadata or {}),
    )


__all__ = ["ResearchEvidenceError", "build_candidate_from_research"]
