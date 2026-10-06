"""ConsistencyEngine：同一 Signal + Level 政策 → 双引擎对比报告。"""

from __future__ import annotations

from typing import Mapping

from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.backtest.fingerprint import compute_semantic_fingerprint
from app.services.research_data.backtest.request import BacktestRequest
from app.services.research_data.backtest.result import BacktestResult
from app.services.research_data.backtest_production import ProductionBacktestEngine
from app.services.research_data.contracts import TargetPosition
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import (
    ConsistencyArtifactStore,
    compute_run_id,
    report_to_run_record,
)
from .attribution import attribute_level_ladder, qlib_vs_prod_gap
from .diff import (
    KNOWN_DIFF_REASONS,
    annotate_position_reasons,
    collect_rejected_diffs,
    compare_cash,
    compare_costs,
    compare_equity,
    compare_positions,
    compare_trades,
    max_abs_diff,
)
from .levels import policies_for_level
from .models import ConsistencyLevel, ConsistencyReport
from .signal_check import check_signal_artifact
from .version import CONSISTENCY_ENGINE_VERSION

# L0 双引擎权益容差；阶梯残差容差
EQUITY_TOLERANCE = 1e-6
# 阶梯残差与权益浮点同量级（禁止真正的 Unknown 大残差）
OTHER_TOLERANCE = 1e-6


class ConsistencyError(RuntimeError):
    """一致性运行失败。"""


class ConsistencyEngine:
    """双引擎一致性对比；无 qlib 时可 production-only（SKIPPED_QLIB）。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        production_engine: ProductionBacktestEngine,
        qlib_engine=None,
        artifact_store: ConsistencyArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._prod = production_engine
        self._qlib = qlib_engine
        self._store = artifact_store or ConsistencyArtifactStore()

    def run(
        self,
        request: BacktestRequest,
        *,
        level: ConsistencyLevel = "L0",
        bars_by_date: Mapping[str, Mapping[str, MarketBar]] | None = None,
        targets_by_date: dict[str, list[TargetPosition]] | None = None,
        run_attribution: bool = True,
        equity_tolerance: float = EQUITY_TOLERANCE,
    ) -> ConsistencyReport:
        """执行指定 Level 的一致性对比并落盘。"""
        exec_p, price_p, cost_p, rules = policies_for_level(level)
        base = request.model_copy(
            update={
                "execution_policy": exec_p,
                "market_price_policy": price_p,
                "cost_policy": cost_p,
                "trading_rule": rules,
            }
        )
        semantic_fp = compute_semantic_fingerprint(base)
        run_id = compute_run_id(semantic_fp, level)

        # Signal 校验（有 artifact 时）
        signal_ok = True
        signal_msg = "injected"
        if base.target_positions_artifact_id and targets_by_date is None:
            try:
                art = self._registry.get_artifact(base.target_positions_artifact_id)
                chk = check_signal_artifact(
                    art, start_date=base.start_date, end_date=base.end_date
                )
                signal_ok = chk.ok
                signal_msg = chk.message
            except Exception as exc:
                signal_ok = False
                signal_msg = str(exc)

        # Production
        prod_req = base.model_copy(update={"engine": "production"})
        prod_result = self._prod.run(
            prod_req,
            bars_by_date=bars_by_date,
            targets_by_date=targets_by_date,
        )

        # Qlib（可选）
        qlib_result: BacktestResult | None = None
        status = "PASSED"
        if self._qlib is not None and targets_by_date is None and bars_by_date is None:
            try:
                qlib_req = base.model_copy(update={"engine": "qlib"})
                qlib_result = self._qlib.run(qlib_req)
            except Exception as exc:
                status = "SKIPPED_QLIB"
                qlib_result = None
                signal_msg = f"{signal_msg}; qlib_error={exc}"
        elif self._qlib is None or bars_by_date is not None:
            status = "SKIPPED_QLIB"

        # Diff
        diffs = []
        diffs.extend(compare_equity(qlib_result, prod_result, tolerance=equity_tolerance))
        diffs.extend(compare_cash(qlib_result, prod_result, tolerance=equity_tolerance))
        pos_diffs = compare_positions(
            qlib_result, prod_result, tolerance=equity_tolerance
        )
        rejected = collect_rejected_diffs(prod_result)
        pos_diffs = annotate_position_reasons(pos_diffs, rejected)
        diffs.extend(pos_diffs)
        diffs.extend(compare_trades(qlib_result, prod_result))
        diffs.extend(compare_costs(qlib_result, prod_result))
        diffs.extend(rejected)

        # Unknown 拒单 → FAILED
        unknown = [
            d
            for d in diffs
            if d.dimension == "rejected"
            and (not d.reason or d.reason not in KNOWN_DIFF_REASONS)
        ]
        if unknown:
            status = "FAILED"

        # L0 且双引擎齐全：大额权益差 → FAILED
        if (
            level == "L0"
            and qlib_result is not None
            and max_abs_diff(diffs, "equity") > equity_tolerance
        ):
            status = "FAILED"

        if not signal_ok:
            status = "FAILED"

        # Attribution
        attribution = []
        if run_attribution:

            def _run_prod(req, **kwargs):
                return self._prod.run(req, **kwargs)

            reject_reasons = [
                t.reject_reason
                for t in prod_result.trades
                if t.status == "REJECTED" and t.reject_reason
            ]
            attribution = attribute_level_ladder(
                base_request=base,
                run_production=_run_prod,
                bars_by_date=bars_by_date,
                targets_by_date=targets_by_date,
                up_to_level=level,
                rejected_reasons=reject_reasons,
            )
            other = next(
                (a for a in attribution if a.component == "other"), None
            )
            if other is not None and abs(other.return_impact) > OTHER_TOLERANCE:
                # 阶梯应闭合；过大残差视为 Unknown
                status = "FAILED"

        max_eq = max_abs_diff(diffs, "equity")
        max_pos = max_abs_diff(diffs, "position")
        gap = qlib_vs_prod_gap(
            qlib_result, prod_result, float(base.initial_capital)
        )

        report = ConsistencyReport(
            run_id=run_id,
            dataset_hash=base.dataset_hash,
            signal_artifact_id=base.target_positions_artifact_id,
            semantic_fingerprint=semantic_fp,
            level=level,
            qlib_result_id=qlib_result.result_id if qlib_result else None,
            qd_result_id=prod_result.result_id,
            diffs=diffs,
            attribution=attribution,
            max_equity_diff=max_eq,
            max_position_diff=max_pos,
            status=status,  # type: ignore[arg-type]
            engine_version=CONSISTENCY_ENGINE_VERSION,
            metadata={
                "signal_check": signal_msg,
                "qlib_prod_return_gap": gap,
                "n_prod_trades": len(prod_result.trades),
                "n_qlib_trades": len(qlib_result.trades) if qlib_result else 0,
            },
        )

        art = self._store.write_report(report)
        try:
            self._registry.upsert_artifact(art)
            self._registry.upsert_consistency_run(report_to_run_record(report))
        except Exception:
            pass
        return report
