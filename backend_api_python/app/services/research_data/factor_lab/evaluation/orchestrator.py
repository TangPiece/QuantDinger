"""FactorEvaluationService：Spec → Plan → Align → Dataset。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import EvaluationDatasetRecord
from app.services.research_data.data_query import DataQuery, DataQueryError
from app.services.research_data.registry import ResearchRegistry

from .align import EvaluationAligner, collect_suspended_from_status
from .artifact_store import EvaluationArtifactStore
from .forward_return import ForwardReturnEngine
from .planner import EvaluationPlanError, build_evaluation_plan
from .protocol import EvaluationFrame, EvaluationPlan, EvaluationSpec
from .writers import EvaluationDatasetWriter


class FactorEvaluationError(RuntimeError):
    """评价端到端失败。"""


@dataclass
class EvaluationResult:
    """评价运行结果。"""

    record: EvaluationDatasetRecord
    frame: EvaluationFrame
    plan: EvaluationPlan


class FactorEvaluationService:
    """Factor Dataset → Evaluation Dataset 编排。"""

    def __init__(
        self,
        query: DataQuery,
        registry: ResearchRegistry,
        store: CanonicalStore,
        *,
        artifact_store: EvaluationArtifactStore | None = None,
    ) -> None:
        self._query = query
        self._registry = registry
        self._store = store
        self._artifacts = artifact_store or EvaluationArtifactStore()
        self._aligner = EvaluationAligner(ForwardReturnEngine())
        self._writer = EvaluationDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def run(
        self,
        spec: EvaluationSpec,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """端到端评价；metadata 可注入 factor_records / instruments 等测试夹具。"""
        meta = dict(metadata or {})
        try:
            factor_ds = self._registry.get_factor_dataset(spec.factor_dataset_id)
        except KeyError as exc:
            raise FactorEvaluationError(
                f"factor_dataset not found: {spec.factor_dataset_id}"
            ) from exc

        plan = build_evaluation_plan(spec, factor_ds)
        plan = plan.model_copy(
            update={"metadata": {**(plan.metadata or {}), **meta}}
        )

        # 幂等：已存在直接返回（仍重建 frame 便于测试断言时可跳过）
        if not meta.get("force_recompute"):
            try:
                existing = self._registry.get_evaluation_dataset(plan.evaluation_hash)
                # 仍构造空 frame 标记；测试需要完整 frame 时走 force 或首次写
                if meta.get("return_existing_only"):
                    return EvaluationResult(
                        record=existing,
                        frame=EvaluationFrame(horizons=list(plan.return_spec.horizons)),
                        plan=plan,
                    )
            except KeyError:
                pass

        factor_rows = self._load_factor_rows(plan, meta)
        instruments = sorted(
            {str(r["instrument_key"]) for r in factor_rows}
            | set(meta.get("instruments") or [])
        )
        if not instruments:
            raise FactorEvaluationError("no instruments for evaluation")

        start = date.fromisoformat(plan.start_date)
        end = date.fromisoformat(plan.end_date)
        # 为 delay+horizon 预留日历缓冲
        buf_days = max(plan.return_spec.horizons) + int(
            plan.return_spec.execution_delay
        ) + 5
        end_buf = date.fromordinal(min(end.toordinal() + buf_days * 2, date.max.toordinal()))

        market = self._query.market(
            instruments,
            start,
            end_buf,
            price_policy=plan.price_policy,
            exchange=plan.exchange,
            snapshot_id=plan.snapshot_id,
        )
        calendar = self._query.trading_calendar(
            instruments,
            start,
            end_buf,
            exchange=plan.exchange,
            price_policy=plan.price_policy,
        )
        if not calendar:
            # 允许纯 weekday 日历兜底（golden 无 weekend bars 时）
            calendar = _weekday_calendar(start, end_buf)

        universe_members = self._resolve_universe(plan, spec, meta)
        suspended = self._load_suspended(instruments, calendar, plan, meta)
        pit_invalid = set(meta.get("pit_invalid") or [])

        frame = self._aligner.align(
            plan=plan,
            spec=spec,
            factor_rows=factor_rows,
            market=market,
            calendar=calendar,
            universe_members=universe_members,
            suspended=suspended,
            pit_invalid=pit_invalid,
        )
        # force_recompute：测试/重算时绕过同 hash 幂等短路
        record = self._writer.write(
            plan, frame, force=bool(meta.get("force_recompute"))
        )
        return EvaluationResult(record=record, frame=frame, plan=plan)

    def _load_factor_rows(
        self, plan: EvaluationPlan, meta: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """优先 metadata 注入；否则从 factor parquet 读取。"""
        if meta.get("factor_records") is not None:
            return list(meta["factor_records"])
        if not plan.factor_ref:
            raise FactorEvaluationError("factor_ref missing on factor dataset")
        try:
            from app.services.research_data import config as rd_config

            prefix = (
                f"{rd_config.canonical_prefix()}/factor/daily/"
                f"factor_set={plan.factor_ref}"
            )
            df = self._query._repo.read_parquet_df(prefix=prefix)  # noqa: SLF001
        except Exception as exc:
            raise FactorEvaluationError(f"failed to load factor panel: {exc}") from exc
        if df is None or df.empty:
            raise FactorEvaluationError(
                f"empty factor panel for {plan.factor_ref}"
            )
        rows = []
        for r in df.to_dict(orient="records"):
            rows.append(
                {
                    "instrument_key": r["instrument_key"],
                    "factor_date": r.get("trading_date") or r.get("factor_date"),
                    "factor_value": r.get("value") or r.get("factor_value"),
                }
            )
        return rows

    def _resolve_universe(
        self,
        plan: EvaluationPlan,
        spec: EvaluationSpec,
        meta: dict[str, Any],
    ) -> set[str]:
        """必须绑定 snapshot；禁止回退当前成分。"""
        if meta.get("universe_members") is not None:
            return set(meta["universe_members"])
        kt = datetime.fromisoformat(plan.end_date).replace(tzinfo=timezone.utc)
        try:
            members = self._query.universe(
                plan.universe_code,
                kt,
                snapshot_id=plan.snapshot_id,
                universe_version=plan.universe_version or spec.universe_version,
            )
        except (DataQueryError, KeyError) as exc:
            raise FactorEvaluationError(
                "historical universe snapshot required; "
                f"refusing current-universe fallback: {exc}"
            ) from exc
        if not members:
            raise FactorEvaluationError(
                f"universe {plan.universe_code} empty for snapshot {plan.snapshot_id}"
            )
        return set(members)

    def _load_suspended(
        self,
        instruments: list[str],
        calendar: list[date],
        plan: EvaluationPlan,
        meta: dict[str, Any],
    ) -> set[tuple[str, date]]:
        if meta.get("suspended") is not None:
            return set(meta["suspended"])
        out: set[tuple[str, date]] = set()
        for d in calendar:
            try:
                st = self._query.trading_status(
                    instruments,
                    d,
                    exchange=plan.exchange,
                    snapshot_id=plan.snapshot_id,
                )
            except Exception:
                continue
            out |= collect_suspended_from_status(st)
        return out


def _weekday_calendar(start: date, end: date) -> list[date]:
    """仅工作日的最小日历（无外部 holiday 源时的测试兜底）。"""
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur = date.fromordinal(cur.toordinal() + 1)
    return out
