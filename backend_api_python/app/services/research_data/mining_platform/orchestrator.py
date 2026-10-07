"""挖掘流水线：Generate → Screen → Dedup → Eval → Holdout → Rank。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.research_data.contracts import FeatureDefinition, PricePolicy
from app.services.research_data.evaluation_platform.policy_presets import get_policy as get_eval_policy

from .dedup import run_dedup
from .expression.ast import ExpressionNode, node_depth
from .expression.canonicalize import expression_hash_from_node
from .expression.lower_dsl import lower_to_dsl
from .feature_universe import FeatureUniverse
from .fsm import advance
from .generators.exhaustive import generate_exhaustive
from .generators.random_search import generate_random
from .holdout import attach_holdout_metrics
from .identity import new_candidate_id
from .policy import MiningPolicy
from .protocol import FactorCandidate, MiningJob, MiningPlatformInject, MiningRunStatus
from .ranking import rank_candidates
from .screen import fast_screen_node


class MiningOrchestratorError(RuntimeError):
    pass


class _FactorSvc(Protocol):
    def register_factor(self, definition: FeatureDefinition) -> FeatureDefinition: ...

    def build_factor(
        self,
        factor_ref: str,
        dataset_ref: str,
        *,
        window: tuple[str, str],
        layout: str = "long",
        inject: Any = None,
    ) -> Any: ...


class _EvalSvc(Protocol):
    def run_evaluation(
        self,
        factor_ref: str,
        dataset_ref: str,
        *,
        policy_id: str = "default_equity_factor_v1",
        window: tuple[str, str] | None = None,
        layout: str = "long",
        inject: Any = None,
    ) -> Any: ...

    def get_quality_score(self, evaluation_id: str) -> Any: ...


@dataclass
class PipelineStats:
    generated: int
    screened: int
    tested: int
    survivors: int
    status: MiningRunStatus


@dataclass
class PipelineResult:
    candidates: list[FactorCandidate]
    stats: PipelineStats
    quality_by_eval: dict[str, float]
    ic_by_eval: dict[str, float]
    scores: list[Any]


def _generate_nodes(
    policy: MiningPolicy, universe: FeatureUniverse, random_seed: int
) -> list[ExpressionNode]:
    if policy.generator == "random_search":
        return generate_random(policy, columns=universe.columns, random_seed=random_seed)
    return generate_exhaustive(policy, columns=universe.columns)


def _factor_ref_for_expression(expression_hash: str) -> tuple[str, str]:
    code = f"MINE_{expression_hash[:16].upper()}"
    version = "1.0.0"
    return f"{code}@{version}", code


class MiningOrchestrator:
    def __init__(
        self,
        *,
        factor_svc: _FactorSvc | None = None,
        eval_svc: _EvalSvc | None = None,
    ) -> None:
        self._factor = factor_svc
        self._eval = eval_svc

    def run(
        self,
        job: MiningJob,
        *,
        policy: MiningPolicy,
        universe: FeatureUniverse,
        handle: Any,
        mining_run_id: str,
        inject: MiningPlatformInject | None = None,
    ) -> PipelineResult:
        status: MiningRunStatus = "RUNNING"
        status = advance(status, "SCREENING")

        nodes = _generate_nodes(policy, universe, job.random_seed)
        generated = len(nodes)

        candidates: list[FactorCandidate] = []
        for node in nodes:
            canon, eh = expression_hash_from_node(node)
            dsl = lower_to_dsl(node)
            candidates.append(
                FactorCandidate(
                    candidate_id=new_candidate_id(),
                    mining_run_id=mining_run_id,
                    expression_hash=eh,
                    dsl_expression=canon,
                    depth=node_depth(node),
                    status="GENERATED",
                )
            )

        screened: list[FactorCandidate] = []
        screened_out = 0
        for c, node in zip(candidates, nodes):
            sr = fast_screen_node(node, policy, inject=inject)
            if sr.passed:
                screened.append(
                    c.model_copy(
                        update={
                            "status": "GENERATED",
                            "metadata": {"proxy_ic": sr.proxy_ic},
                        }
                    )
                )
            else:
                screened_out += 1
                screened.append(c.model_copy(update={"status": "SCREENED_OUT"}))

        passed = [c for c in screened if c.status != "SCREENED_OUT"]
        dedup_res = run_dedup(
            passed,
            dedup_expression=policy.dedup_by_expression_hash,
            corr_enabled=policy.corr_dedup_enabled,
            corr_threshold=policy.corr_redundancy_threshold,
            corr_top_n=policy.corr_dedup_top_n,
            inject=inject,
        )
        survivors = [
            c for c in dedup_res.survivors if c.status not in ("REDUNDANT", "DEDUP_REMOVED")
        ]
        survivors = survivors[: policy.max_full_evaluations]

        status = advance(status, "EVALUATING")
        eval_policy = get_eval_policy(job.evaluation_policy_id)
        eval_version = eval_policy.version

        quality_by_eval: dict[str, float] = {}
        ic_by_eval: dict[str, float] = {}
        evaluated: list[FactorCandidate] = []
        tested = 0

        train_window = (job.train_start, job.train_end)
        holdout_window: tuple[str, str] | None = None
        if job.holdout_start and job.holdout_end:
            holdout_window = (job.holdout_start, job.holdout_end)

        eval_inject = None
        if inject and inject.evaluation_inject:
            eval_inject = inject.evaluation_inject

        for c in survivors:
            tested += 1
            factor_ref, code = _factor_ref_for_expression(c.expression_hash)
            try:
                if inject and inject.skip_build_eval:
                    eid = f"eval_inject_{c.expression_hash[:12]}"
                    qt = 0.5
                    ic = float(c.metadata.get("proxy_ic", 0.05))
                    if inject.synthetic_evaluation_scores:
                        qt = float(
                            inject.synthetic_evaluation_scores.get(c.expression_hash, qt)
                        )
                    quality_by_eval[eid] = qt
                    ic_by_eval[eid] = ic
                    ec = c.model_copy(
                        update={
                            "status": "EVALUATED",
                            "factor_ref": factor_ref,
                            "evaluation_id": eid,
                        }
                    )
                else:
                    if self._factor is None or self._eval is None:
                        raise MiningOrchestratorError("factor_svc and eval_svc required")
                    feat = FeatureDefinition(
                        code=code,
                        version="1.0.0",
                        name=f"Mined {c.dsl_expression[:48]}",
                        expression=c.dsl_expression,
                        factor_type="TECHNICAL",
                        computation_engine="quantdinger",
                        dependencies=["market:CNStock"],
                        information_policy="NON_PIT",
                        price_policy=PricePolicy(adjustment="none"),
                        definition={
                            "lifecycle_status": "DRAFT",
                            "mined": True,
                            "expression_hash": c.expression_hash,
                        },
                    )
                    self._factor.register_factor(feat)
                    self._factor.build_factor(
                        factor_ref,
                        job.dataset_ref,
                        window=train_window,
                        layout=job.layout,
                        inject=eval_inject,
                    )
                    ev_run = self._eval.run_evaluation(
                        factor_ref,
                        job.dataset_ref,
                        policy_id=job.evaluation_policy_id,
                        window=train_window,
                        layout=job.layout,
                        inject=eval_inject,
                    )
                    if ev_run.status != "SUCCESS":
                        ec = c.model_copy(update={"status": "FAILED", "factor_ref": factor_ref})
                        evaluated.append(ec)
                        continue
                    score = self._eval.get_quality_score(ev_run.evaluation_id)
                    qt = float(score.total_score)
                    ic_raw = score.raw_metrics.get("ic_by_horizon") or {}
                    ic = 0.0
                    if ic_raw:
                        first = next(iter(ic_raw.values()), {})
                        ic = abs(float(first.get("mean_ic") or 0.0))
                    quality_by_eval[ev_run.evaluation_id] = qt
                    ic_by_eval[ev_run.evaluation_id] = ic
                    ec = c.model_copy(
                        update={
                            "status": "EVALUATED",
                            "factor_ref": factor_ref,
                            "evaluation_id": ev_run.evaluation_id,
                        }
                    )
                holdout_meta = None
                if holdout_window:
                    holdout_meta = {
                        "holdout_start": holdout_window[0],
                        "holdout_end": holdout_window[1],
                        "selection_excluded": True,
                    }
                ec = attach_holdout_metrics(
                    ec,
                    holdout_eval_id=(
                        f"holdout_{c.expression_hash[:12]}" if holdout_window else ""
                    ),
                    metrics=holdout_meta,
                    inject=inject,
                )
                evaluated.append(ec)
            except Exception as exc:
                evaluated.append(
                    c.model_copy(
                        update={"status": "FAILED", "metadata": {"error": str(exc)}}
                    )
                )

        status = advance(status, "RANKING")
        ranked, mining_scores = rank_candidates(
            evaluated,
            quality_by_eval_id=quality_by_eval,
            ic_by_eval_id=ic_by_eval,
        )

        # 合并：未进入 full eval 的保留原状态
        ranked_ids = {c.candidate_id for c in ranked}
        final: list[FactorCandidate] = []
        for c in screened:
            if c.candidate_id in ranked_ids:
                final.append(next(x for x in ranked if x.candidate_id == c.candidate_id))
            else:
                final.append(c)
        for c in ranked:
            if c.candidate_id not in {x.candidate_id for x in final}:
                final.append(c)

        status = advance(status, "COMPLETED")
        _ = eval_version
        _ = handle

        return PipelineResult(
            candidates=final,
            stats=PipelineStats(
                generated=generated,
                screened=len(passed),
                tested=tested,
                survivors=len(ranked),
                status=status,
            ),
            quality_by_eval=quality_by_eval,
            ic_by_eval=ic_by_eval,
            scores=list(mining_scores),
        )


__all__ = ["MiningOrchestrator", "MiningOrchestratorError", "PipelineResult"]
