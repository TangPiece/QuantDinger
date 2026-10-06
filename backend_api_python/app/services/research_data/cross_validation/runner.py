"""CrossValidationService：编排 5B/5D + 分层 Diff。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import (
    CrossValidationSummary,
    StrategyResearchSummary,
)
from app.services.research_data.qlib_strategy import (
    QlibStrategyService,
    QlibStrategySpec,
)
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.research_backtest import (
    BacktestSpec,
    ResearchBacktestService,
    ResearchExecutionPolicy,
)

from .artifact_store import CrossValidationArtifactStore
from .attribution import attribute_differences
from .dataset_diff import diff_dataset
from .execution_diff import diff_execution
from .hash import compute_cv_hash
from .loaders import (
    build_prediction_records,
    build_weight_records,
    load_qlib_nav_curve,
    load_qlib_predictions,
    load_qlib_weights,
    qd_nav_from_frames,
    qd_nav_from_storage,
    strategy_identity,
    summarize_bars,
)
from .nav_diff import diff_nav
from .performance_diff import build_side_by_side, diff_performance
from .pit_diff import diff_pit
from .portfolio_diff import diff_portfolio
from .protocol import (
    CrossValidationReport,
    CrossValidationSpec,
    ENGINE_VERSION,
    LayerResult,
)
from .report import build_report
from .signal_diff import diff_signal
from .universe_diff import diff_universe
from .writers import CrossValidationWriter


class CrossValidationError(RuntimeError):
    """交叉验证失败。"""


@dataclass
class CrossValidationResult:
    """运行结果。"""

    cv_hash: str
    summary: CrossValidationSummary
    report: CrossValidationReport
    layers: list[LayerResult] = field(default_factory=list)


class CrossValidationService:
    """同一 strategy_hash 上比较 ResearchBacktest 与 QlibRun。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        backtest_svc: ResearchBacktestService | None = None,
        qlib_svc: QlibStrategyService | None = None,
        artifact_store: CrossValidationArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._bt = backtest_svc or ResearchBacktestService(store, registry)
        self._ql = qlib_svc or QlibStrategyService(store, registry)
        self._artifacts = artifact_store or CrossValidationArtifactStore()
        self._writer = CrossValidationWriter(registry, artifact_store=self._artifacts)

    def run(
        self,
        strategy_hash: str,
        spec: CrossValidationSpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> CrossValidationResult:
        """resolve → 跑/加载 5B+5D → L1–L7 + attribution → persist。"""
        meta = dict(metadata or {})
        strategy = self._resolve_strategy(strategy_hash, meta)
        if spec is None:
            start = _parse_date(meta.get("start_date"))
            end = _parse_date(meta.get("end_date"))
            if start is None or end is None:
                raise CrossValidationError(
                    "start_date and end_date required when spec is None"
                )
            mode = str(meta.get("execution_policy") or "NEXT_OPEN")
            spec = CrossValidationSpec(
                strategy_hash=strategy_hash,
                start_date=start,
                end_date=end,
                backtest_hash=str(meta.get("backtest_hash") or ""),
                qlib_run_hash=str(meta.get("qlib_run_hash") or ""),
                execution_policy=ResearchExecutionPolicy(mode=mode),  # type: ignore[arg-type]
                realism=str(meta.get("realism") or "GROSS"),  # type: ignore[arg-type]
                market_rule=str(meta.get("market_rule") or "CN_A"),
                initial_nav=float(meta.get("initial_nav") or 1.0),
            )
        elif spec.strategy_hash != strategy_hash:
            spec = spec.model_copy(update={"strategy_hash": strategy_hash})

        skip_engine = bool(meta.get("skip_engine_run"))
        force = bool(meta.get("force_recompute"))

        # --- 5B ---
        bt_summary = None
        bt_frames = None
        bhash = spec.backtest_hash
        if bhash and skip_engine:
            bt_summary = self._registry.get_research_backtest(bhash)
        elif not skip_engine:
            bspec = BacktestSpec(
                strategy_hash=strategy_hash,
                start_date=spec.start_date,
                end_date=spec.end_date,
                execution_policy=spec.execution_policy,
                realism=spec.realism,  # type: ignore[arg-type]
                market_rule=spec.market_rule,  # type: ignore[arg-type]
                initial_nav=spec.initial_nav,
            )
            bt_meta = {
                k: meta[k]
                for k in (
                    "targets_by_date",
                    "target_positions",
                    "price_bars",
                    "cost_policy_override",
                    "trading_rule_override",
                    "trading_status_by_date",
                )
                if k in meta
            }
            bt_meta["force_recompute"] = force
            br = self._bt.run(strategy_hash, bspec, metadata=bt_meta)
            bhash = br.backtest_hash
            bt_summary = br.summary
            bt_frames = br.frames
            spec = spec.model_copy(update={"backtest_hash": bhash})
        elif bhash:
            bt_summary = self._registry.get_research_backtest(bhash)
        else:
            raise CrossValidationError("backtest_hash required when skip_engine_run")

        # --- 5D ---
        ql_summary = None
        qhash = spec.qlib_run_hash
        ql_weights_mem = None
        ql_pred_mem = None
        if qhash and skip_engine:
            ql_summary = self._registry.get_research_qlib_run(qhash)
        elif not skip_engine:
            qspec = QlibStrategySpec(
                strategy_hash=strategy_hash,
                start_date=spec.start_date,
                end_date=spec.end_date,
                execution_policy=spec.execution_policy,
                realism=spec.realism,  # type: ignore[arg-type]
                market_rule=spec.market_rule,  # type: ignore[arg-type]
                initial_nav=spec.initial_nav,
                dataset_ref=str(meta.get("dataset_ref") or ""),
                materialization_id=str(meta.get("materialization_id") or ""),
                dataset_hash=str(meta.get("dataset_hash") or ""),
            )
            ql_meta = {
                k: meta[k]
                for k in (
                    "targets_by_date",
                    "target_positions",
                    "signal_rows",
                    "price_bars",
                    "skip_ensure_cache",
                    "materialization_id",
                    "dataset_hash",
                    "dataset_ref",
                    "force_inprocess",
                    "force_synthetic",
                    "cost_policy_override",
                    "trading_rule_override",
                )
                if k in meta
            }
            ql_meta["force_recompute"] = force
            ql_meta["backtest_hash"] = bhash
            # 无 cache 时默认合成
            ql_meta.setdefault("force_synthetic", True)
            ql_meta.setdefault("force_inprocess", True)
            ql_meta.setdefault("skip_ensure_cache", True)
            qr = self._ql.run(strategy_hash, qspec, metadata=ql_meta)
            qhash = qr.qlib_run_hash
            ql_summary = qr.summary
            ql_weights_mem = qr.weights
            ql_pred_mem = qr.predictions
            spec = spec.model_copy(update={"qlib_run_hash": qhash})
        elif qhash:
            ql_summary = self._registry.get_research_qlib_run(qhash)
        else:
            raise CrossValidationError("qlib_run_hash required when skip_engine_run")

        # hash 在配对后重算（含 backtest/qlib hash）
        cv_hash = compute_cv_hash(spec)
        if not force:
            try:
                existing = self._registry.get_research_cross_validation(cv_hash)
                # 重建最小 report
                from .protocol import AttributionBreakdown

                report = CrossValidationReport(
                    cv_hash=cv_hash,
                    strategy_hash=strategy_hash,
                    backtest_hash=existing.backtest_hash,
                    qlib_run_hash=existing.qlib_run_hash,
                    start_date=existing.start_date,
                    end_date=existing.end_date,
                    realism=existing.realism,
                    status=existing.status,  # type: ignore[arg-type]
                    attribution=AttributionBreakdown.model_validate(
                        existing.attribution_json or {}
                    ),
                    side_by_side=dict(existing.metrics_side_by_side_json or {}),
                    engine_version=existing.engine_version or ENGINE_VERSION,
                )
                return CrossValidationResult(
                    cv_hash=cv_hash, summary=existing, report=report
                )
            except KeyError:
                pass

        # --- Diff 输入 ---
        id_meta = {
            "dataset_ref": (ql_summary.dataset_ref if ql_summary else "")
            or meta.get("dataset_ref"),
            "materialization_id": (
                ql_summary.materialization_id if ql_summary else ""
            )
            or meta.get("materialization_id"),
            "dataset_hash": (ql_summary.dataset_hash if ql_summary else "")
            or meta.get("dataset_hash"),
            "factor_dataset_id": meta.get("factor_dataset_id"),
            "universe_code": meta.get("universe_code"),
            "snapshot_id": meta.get("snapshot_id"),
        }
        qd_id = strategy_identity(strategy, meta=id_meta)
        # Qlib 侧与同一 strategy 共享 universe/snapshot；补 materialization
        ql_id = dict(qd_id)
        if ql_summary:
            ql_id["dataset_ref"] = ql_summary.dataset_ref or ql_id.get("dataset_ref")
            ql_id["materialization_id"] = (
                ql_summary.materialization_id or ql_id.get("materialization_id")
            )
            ql_id["dataset_hash"] = ql_summary.dataset_hash or ql_id.get("dataset_hash")
        # 注入场景钉住同一 mat
        if meta.get("materialization_id"):
            qd_id["materialization_id"] = str(meta["materialization_id"])
            ql_id["materialization_id"] = str(meta["materialization_id"])
        if meta.get("dataset_hash"):
            qd_id["dataset_hash"] = str(meta["dataset_hash"])
            ql_id["dataset_hash"] = str(meta["dataset_hash"])
        if meta.get("snapshot_id"):
            qd_id["snapshot_id"] = str(meta["snapshot_id"])
            ql_id["snapshot_id"] = str(meta["snapshot_id"])
        if meta.get("universe_code"):
            qd_id["universe_code"] = str(meta["universe_code"])
            ql_id["universe_code"] = str(meta["universe_code"])

        bar_sum = summarize_bars(meta.get("price_bars"))
        signal_rows = list(meta.get("signal_rows") or [])
        targets = meta.get("targets_by_date")

        qd_pred = build_prediction_records(
            signal_rows, start=spec.start_date, end=spec.end_date
        )
        if ql_pred_mem is not None and not getattr(ql_pred_mem, "empty", True):
            import pandas as pd

            ql_pred = [
                {
                    "datetime": str(pd.Timestamp(dt).date()),
                    "instrument": str(inst),
                    "score": float(v),
                }
                for (dt, inst), v in ql_pred_mem.items()
            ]
        elif ql_summary and ql_summary.storage_uri:
            ql_pred = load_qlib_predictions(ql_summary.storage_uri)
        else:
            ql_pred = list(qd_pred)

        qd_w = build_weight_records(
            targets, start=spec.start_date, end=spec.end_date
        )
        if ql_weights_mem is not None and not getattr(ql_weights_mem, "empty", True):
            import pandas as pd

            ql_w = [
                {
                    "datetime": str(pd.Timestamp(dt).date()),
                    "instrument": str(inst),
                    "weight": float(v),
                }
                for (dt, inst), v in ql_weights_mem.items()
            ]
        elif ql_summary and ql_summary.storage_uri:
            ql_w = load_qlib_weights(ql_summary.storage_uri)
        else:
            ql_w = list(qd_w)

        if bt_frames is not None:
            qd_nav = qd_nav_from_frames(bt_frames.nav)
            # 补 portfolio_return
            ret_by = {
                str(r.trading_date)[:10]: r.portfolio_return
                for r in bt_frames.returns
            }
            for row in qd_nav:
                row["portfolio_return"] = ret_by.get(row["trading_date"])
        elif bt_summary and bt_summary.storage_uri:
            qd_nav = qd_nav_from_storage(bt_summary.storage_uri)
        else:
            qd_nav = []

        if ql_summary and ql_summary.storage_uri:
            ql_nav = load_qlib_nav_curve(ql_summary.storage_uri)
        else:
            ql_nav = []

        tol = spec.tolerances
        layers: list[LayerResult] = [
            diff_dataset(qd_id, ql_id, bar_summary=bar_sum),
            diff_pit(
                signal_rows,
                future_leak_rows=meta.get("future_leak_rows"),
            ),
            diff_universe(
                qd_id,
                ql_id,
                qd_membership=meta.get("universe_membership"),
                qlib_membership=meta.get("universe_membership"),
            ),
            diff_signal(qd_pred, ql_pred, abs_tol=tol.signal_abs),
            diff_portfolio(qd_w, ql_w, abs_tol=tol.weight_abs),
            diff_execution(
                {
                    "mode": spec.execution_policy.mode,
                    "fill_field": spec.execution_policy.fill_field,
                },
                {
                    "mode": (ql_summary.execution_policy if ql_summary else "")
                    or spec.execution_policy.mode,
                    "fill_field": spec.execution_policy.fill_field,
                },
                compatibility=(
                    ql_summary.compatibility_json if ql_summary else None
                ),
                realism=spec.realism,
            ),
            diff_nav(
                qd_nav, ql_nav, abs_tol=tol.nav_abs, rel_tol=tol.nav_rel
            ),
            diff_performance(
                bt_summary.metrics_json if bt_summary else {},
                ql_summary.metrics_json if ql_summary else {},
                abs_tol=tol.perf_abs,
            ),
        ]

        qd_ret = (bt_summary.metrics_json or {}).get("total_return") if bt_summary else None
        ql_ret = (ql_summary.metrics_json or {}).get("total_return") if ql_summary else None
        attr = attribute_differences(
            layers,
            qd_total_return=float(qd_ret) if qd_ret is not None else None,
            qlib_total_return=float(ql_ret) if ql_ret is not None else None,
            compatibility=ql_summary.compatibility_json if ql_summary else None,
            realism=spec.realism,
            other_tol=tol.other_abs,
        )
        turnover_qd = (bt_summary.metrics_json or {}).get("mean_turnover") if bt_summary else None
        side = build_side_by_side(
            bt_summary.metrics_json if bt_summary else {},
            ql_summary.metrics_json if ql_summary else {},
            universe_n=len(meta.get("universe_membership") or [])
            or bar_sum.get("n_instruments"),
            turnover_qd=float(turnover_qd) if turnover_qd is not None else None,
        )
        report = build_report(
            cv_hash=cv_hash,
            strategy_hash=strategy_hash,
            backtest_hash=bhash or "",
            qlib_run_hash=qhash or "",
            start_date=spec.start_date.isoformat(),
            end_date=spec.end_date.isoformat(),
            realism=spec.realism,
            layers=layers,
            attribution=attr,
            side_by_side=side,
            metadata={
                "engine_version": ENGINE_VERSION,
                "qd_engine": getattr(bt_summary, "engine_version", ""),
                "qlib_engine": getattr(ql_summary, "engine_version", ""),
            },
            other_tol=tol.other_abs,
        )
        summary = self._writer.write(spec, cv_hash=cv_hash, report=report, force=force)
        return CrossValidationResult(
            cv_hash=cv_hash,
            summary=summary,
            report=report,
            layers=layers,
        )

    def _resolve_strategy(
        self, strategy_hash: str, meta: dict[str, Any]
    ) -> StrategyResearchSummary | None:
        try:
            return self._registry.get_strategy_research(strategy_hash)
        except KeyError:
            if (
                meta.get("targets_by_date") is not None
                or meta.get("signal_rows") is not None
            ):
                return None
            raise CrossValidationError(
                f"strategy_research not found: {strategy_hash}"
            ) from None


def _parse_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not hasattr(v, "hour"):
        return v
    return date.fromisoformat(str(v)[:10])
