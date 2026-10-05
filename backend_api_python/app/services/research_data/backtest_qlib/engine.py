"""QlibResearchBacktestEngine：Domain BacktestRequest → Qlib → BacktestResult。

流程锁定见 docs/backtest/07_qlib_research_backtest.md。
"""

from __future__ import annotations

import sys
from typing import Any

from app.services.research_data.backtest.fingerprint import compute_request_fingerprint
from app.services.research_data.backtest.request import BacktestRequest
from app.services.research_data.backtest.result import BacktestResult
from app.services.research_data.backtest.version import BACKTEST_CONTRACT_VERSION
from app.services.research_data.contracts import ExperimentDefinition
from app.services.research_data.qlib_adapter import QlibAdapter, default_runtime
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import BacktestArtifactStore, compute_result_id
from .config_builder import build_backtest_config
from .exchange_map import map_exchange_kwargs
from .mlflow_log import log_backtest_to_mlflow
from .result_mapper import map_qlib_outputs
from .signal_loader import load_target_weight_series
from .version import QLIB_BACKTEST_ENGINE_VERSION
from .weight_strategy import QuantDingerWeightStrategy


class QlibBacktestError(RuntimeError):
    """Qlib Research 回测失败。"""


class QlibResearchBacktestEngine:
    """实现 BacktestEngine Protocol：仅支持 engine=qlib。"""

    def __init__(
        self,
        qlib_adapter: QlibAdapter,
        registry: ResearchRegistry,
        *,
        artifact_store: BacktestArtifactStore | None = None,
        runtime=None,
    ) -> None:
        """
        Args:
            qlib_adapter: 用于 ensure_cache / 解析 dataset
            registry: Experiment / Artifact 索引
            artifact_store: 回测结果落盘；默认 research_cache
            runtime: QlibRuntime；默认进程级 default_runtime
        """
        self._adapter = qlib_adapter
        self._registry = registry
        self._store = artifact_store or BacktestArtifactStore()
        self._runtime = runtime or default_runtime

    def run(self, request: BacktestRequest) -> BacktestResult:
        """执行研究回测并返回标准化 BacktestResult。"""
        if request.engine != "qlib":
            raise QlibBacktestError(
                f"QlibResearchBacktestEngine only supports engine='qlib', got {request.engine!r}"
            )

        experiment = self._registry.get_experiment(request.experiment_id)
        if experiment.dataset_hash != request.dataset_hash:
            raise QlibBacktestError(
                "dataset_hash mismatch: "
                f"request={request.dataset_hash!r} experiment={experiment.dataset_hash!r}"
            )

        artifact_id = request.target_positions_artifact_id
        if not artifact_id:
            raise QlibBacktestError("target_positions_artifact_id is required")
        signal_art = self._registry.get_artifact(artifact_id)

        weights = load_target_weight_series(
            signal_art,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        dataset_ref = request.dataset_ref or experiment.dataset_ref
        if not dataset_ref:
            raise QlibBacktestError("dataset_ref missing on request and experiment")

        cache = self._adapter.ensure_cache(dataset_ref)
        # Qlib 闭区间：最后一根 bar 需要 calendar[i+1]；golden 稀疏日历需垫一天
        from .calendar_pad import ensure_calendar_pad

        ensure_calendar_pad(cache.cache_path, after_date=request.end_date, pad_days=1)
        self._runtime.activate(cache.cache_path, kernels=1, force=True)

        strategy = QuantDingerWeightStrategy(target_weights=weights, risk_degree=1.0)
        exchange_kwargs = map_exchange_kwargs(request)
        # 限制 codes 为权重中出现的标的，加速且避免全市场扫描
        instruments = sorted(
            {str(i) for i in weights.index.get_level_values("instrument").unique()}
        )
        if instruments:
            exchange_kwargs["codes"] = instruments

        bt_kwargs = build_backtest_config(
            request, strategy=strategy, exchange_kwargs=exchange_kwargs
        )

        try:
            from qlib.backtest import backtest as qlib_backtest
        except ImportError as exc:
            raise QlibBacktestError("pyqlib is required for QlibResearchBacktestEngine") from exc

        try:
            portfolio_dict, indicator_dict = qlib_backtest(**bt_kwargs)
        except Exception as exc:
            raise QlibBacktestError(f"qlib.backtest.backtest failed: {exc}") from exc

        mapped = map_qlib_outputs(portfolio_dict, indicator_dict)
        fingerprint = compute_request_fingerprint(request)
        result_id = compute_result_id(fingerprint)

        qlib_py = None
        try:
            import qlib as _qlib

            qlib_py = getattr(_qlib, "__version__", None)
        except Exception:
            qlib_py = None

        metadata: dict[str, Any] = {
            "provider_uri": str(cache.cache_path),
            "signal_artifact_id": artifact_id,
            "dataset_ref": dataset_ref,
            "qlib_py_version": qlib_py,
            "python_version": sys.version.split()[0],
            "materialization_id": cache.materialization_id,
            "weight_days": int(weights.index.get_level_values("datetime").nunique()),
            "weight_instruments": instruments,
        }

        result = BacktestResult(
            result_id=result_id,
            request_fingerprint=fingerprint,
            experiment_id=request.experiment_id,
            dataset_hash=request.dataset_hash,
            engine="qlib",
            engine_version=QLIB_BACKTEST_ENGINE_VERSION,
            contract_version=request.contract_version or BACKTEST_CONTRACT_VERSION,
            equity_curve=mapped["equity_curve"],
            trades=mapped["trades"],
            position_history=mapped["position_history"],
            portfolio_history=mapped["portfolio_history"],
            metrics=mapped["metrics"],
            artifact_uris={},
            metadata=metadata,
        )

        # write_result 会就地回写 result.artifact_uris
        art = self._store.write_result(result, report=mapped.get("report"))
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            # Registry 写入失败不阻断主结果
            pass

        mlflow_run_id = getattr(experiment, "mlflow_run_id", None)
        logged = log_backtest_to_mlflow(result, mlflow_run_id=mlflow_run_id)
        if logged:
            result.metadata["mlflow_run_id"] = logged

        return result


def request_from_experiment(
    experiment: ExperimentDefinition,
    *,
    start_date: str,
    end_date: str,
    initial_capital: float,
    execution_policy,
    market_price_policy,
    cost_policy=None,
    trading_rule=None,
    benchmark: str | None = None,
) -> BacktestRequest:
    """便捷：从 Experiment + research_qlib_relaxed 政策构造 Request。"""
    return BacktestRequest.from_experiment(
        experiment,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        engine="qlib",
        execution_policy=execution_policy,
        market_price_policy=market_price_policy,
        cost_policy=cost_policy,
        trading_rule=trading_rule,
    ).model_copy(update={"benchmark": benchmark})
