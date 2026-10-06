"""QlibStrategyService：5A Strategy → 适配 → spawn Qlib → Summary。"""

from __future__ import annotations

import json
import multiprocessing as mp
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import (
    QlibRunSummary,
    StrategyResearchSummary,
)
from app.services.research_data.qlib_adapter import QlibAdapter
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.research_backtest.loader import load_targets_by_date
from app.services.research_data.research_backtest.protocol import (
    ResearchExecutionPolicy,
)

from .artifact_store import QlibRunArtifactStore
from .backtest_adapter import build_worker_payload, synthetic_weight_nav
from .dataset_adapter import ensure_strategy_cache, resolve_dataset_ref
from .execution_adapter import build_compatibility
from .hash import compute_qlib_run_hash
from .portfolio_adapter import targets_to_weight_series
from .protocol import ENGINE_VERSION, QlibStrategySpec
from .signal_adapter import to_prediction_series
from .writers import QlibRunWriter
from . import worker_main


class QlibStrategyError(RuntimeError):
    """Qlib 策略适配失败。"""


@dataclass
class QlibRunResult:
    qlib_run_hash: str
    summary: QlibRunSummary
    weights: pd.Series | None = None
    predictions: pd.Series | None = None
    strategy: StrategyResearchSummary | None = None
    worker_mode: str = ""


class QlibStrategyService:
    """将 Strategy Contract 适配为可替换 Qlib Research Engine。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        qlib_adapter: QlibAdapter | None = None,
        artifact_store: QlibRunArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._qlib = qlib_adapter
        self._artifacts = artifact_store or QlibRunArtifactStore()
        self._writer = QlibRunWriter(registry, artifact_store=self._artifacts)

    def run(
        self,
        strategy_hash: str,
        spec: QlibStrategySpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> QlibRunResult:
        """resolve → adapt → spawn/inprocess backtest → persist。"""
        meta = dict(metadata or {})
        strategy = self._resolve_strategy(strategy_hash, meta)
        if spec is None:
            start = _parse_date(meta.get("start_date"))
            end = _parse_date(meta.get("end_date"))
            if start is None or end is None:
                raise QlibStrategyError(
                    "start_date and end_date required when spec is None"
                )
            mode = str(meta.get("execution_policy") or "NEXT_OPEN")
            spec = QlibStrategySpec(
                strategy_hash=strategy_hash,
                start_date=start,
                end_date=end,
                execution_policy=ResearchExecutionPolicy(mode=mode),  # type: ignore[arg-type]
                realism=str(meta.get("realism") or "GROSS"),  # type: ignore[arg-type]
                market_rule=str(meta.get("market_rule") or "CN_A"),  # type: ignore[arg-type]
                initial_nav=float(meta.get("initial_nav") or 1.0),
                dataset_ref=str(meta.get("dataset_ref") or ""),
                region=str(meta.get("region") or "cn"),
                metadata={
                    k: meta[k]
                    for k in ("cost_policy_override", "trading_rule_override")
                    if k in meta
                },
            )
        elif spec.strategy_hash != strategy_hash:
            spec = spec.model_copy(update={"strategy_hash": strategy_hash})

        # dataset
        dataset_ref = resolve_dataset_ref(strategy, spec, metadata=meta)
        if dataset_ref and not spec.dataset_ref:
            spec = spec.model_copy(update={"dataset_ref": dataset_ref})

        mat = ensure_strategy_cache(
            self._qlib,
            dataset_ref,
            force=bool(meta.get("force_materialize")),
            metadata=meta,
        )
        if mat is not None:
            spec = spec.model_copy(
                update={
                    "materialization_id": mat.materialization_id,
                    "dataset_hash": getattr(mat, "dataset_hash", None)
                    or spec.dataset_hash
                    or "",
                }
            )
        elif meta.get("materialization_id"):
            spec = spec.model_copy(
                update={
                    "materialization_id": str(meta["materialization_id"]),
                    "dataset_hash": str(
                        meta.get("dataset_hash") or spec.dataset_hash or ""
                    ),
                }
            )

        qhash = compute_qlib_run_hash(spec)
        force = bool(meta.get("force_recompute"))
        injected = (
            meta.get("targets_by_date") is not None
            or meta.get("target_positions") is not None
            or meta.get("signal_rows") is not None
        )
        if not force and not injected:
            try:
                summary = self._registry.get_research_qlib_run(qhash)
                return QlibRunResult(
                    qlib_run_hash=qhash, summary=summary, strategy=strategy
                )
            except KeyError:
                pass

        targets = load_targets_by_date(
            self._store, strategy_hash, metadata=meta
        )
        if not targets and meta.get("target_positions") is None:
            # 允许仅 signal 注入的测试
            if meta.get("signal_rows") is None and meta.get("prediction_series") is None:
                raise QlibStrategyError(
                    f"no target positions for strategy_hash={strategy_hash}"
                )

        weights = targets_to_weight_series(
            targets, start=spec.start_date, end=spec.end_date
        )
        if meta.get("prediction_series") is not None:
            predictions = meta["prediction_series"]
            if not isinstance(predictions, pd.Series):
                predictions = to_prediction_series(list(predictions))
        elif meta.get("signal_rows") is not None:
            predictions = to_prediction_series(
                list(meta["signal_rows"]),
                start=spec.start_date,
                end=spec.end_date,
            )
        else:
            # 无独立 signal 时用权重作弱 prediction 占位（score=weight）
            predictions = weights.rename("score") if not weights.empty else weights

        compat = build_compatibility(spec)
        cache_path = ""
        if mat is not None:
            cache_path = str(getattr(mat, "cache_path", "") or "")
        elif meta.get("cache_path"):
            cache_path = str(meta["cache_path"])

        payload = build_worker_payload(
            spec,
            weights=weights,
            cache_path=cache_path,
            materialization_id=spec.materialization_id,
        )
        # 无 cache 时强制合成标记
        if not cache_path or meta.get("force_synthetic"):
            payload["force_synthetic"] = True

        force_inprocess = bool(meta.get("force_inprocess", True if not cache_path else False))
        worker_result = self._run_worker(payload, force_inprocess=force_inprocess)

        metrics = dict(worker_result.get("metrics") or {})
        mode = str(worker_result.get("mode") or "")
        # 合成 NAV：无真实 Qlib 结果时用 price_bars
        if (
            metrics.get("total_return") is None
            and meta.get("price_bars") is not None
            and not weights.empty
        ):
            syn = synthetic_weight_nav(
                weights,
                meta["price_bars"],
                initial_nav=spec.initial_nav,
                fill_field=spec.execution_policy.fill_field,
                start=spec.start_date,
                end=spec.end_date,
            )
            metrics.update(syn)
            mode = mode or "synthetic_weight_nav"

        metrics["compatibility_has_partial"] = compat.has_partial
        metrics["compatibility_has_unsupported"] = compat.has_unsupported
        metrics["worker_mode"] = mode

        summary = self._writer.write(
            spec,
            qlib_run_hash=qhash,
            compatibility=compat,
            metrics=metrics,
            weights=weights,
            predictions=predictions if isinstance(predictions, pd.Series) else None,
            force=force,
        )
        return QlibRunResult(
            qlib_run_hash=qhash,
            summary=summary,
            weights=weights,
            predictions=predictions if isinstance(predictions, pd.Series) else None,
            strategy=strategy,
            worker_mode=mode,
        )

    def _run_worker(
        self, payload: dict[str, Any], *, force_inprocess: bool
    ) -> dict[str, Any]:
        """默认 spawn；测试可 inprocess。"""
        with tempfile.TemporaryDirectory(prefix="qd_qlib_run_") as tmp:
            tmp_path = Path(tmp)
            payload_path = tmp_path / "payload.json"
            result_path = tmp_path / "result.json"
            payload_path.write_text(
                json.dumps(payload, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            if force_inprocess:
                code = worker_main.run_worker(str(payload_path), str(result_path))
                raw = json.loads(result_path.read_text(encoding="utf-8"))
                if code != 0 and not raw.get("ok"):
                    raise QlibStrategyError(raw.get("error") or "worker failed")
                return raw

            ctx = mp.get_context("spawn")
            proc = ctx.Process(
                target=_spawn_entry,
                args=(str(payload_path), str(result_path)),
            )
            proc.start()
            proc.join(timeout=600)
            if proc.is_alive():
                proc.terminate()
                raise QlibStrategyError("qlib worker timeout")
            if not result_path.is_file():
                raise QlibStrategyError("qlib worker produced no result")
            raw = json.loads(result_path.read_text(encoding="utf-8"))
            if proc.exitcode not in (0, None) and not raw.get("ok"):
                raise QlibStrategyError(raw.get("error") or "worker failed")
            return raw

    def _resolve_strategy(
        self, strategy_hash: str, meta: dict[str, Any]
    ) -> StrategyResearchSummary | None:
        try:
            return self._registry.get_strategy_research(strategy_hash)
        except KeyError:
            if (
                meta.get("targets_by_date") is not None
                or meta.get("target_positions") is not None
                or meta.get("signal_rows") is not None
            ):
                return None
            raise QlibStrategyError(
                f"strategy_research not found: {strategy_hash}"
            ) from None


def _spawn_entry(payload_path: str, result_path: str) -> None:
    """spawn 目标：必须为模块级函数。"""
    raise SystemExit(worker_main.run_worker(payload_path, result_path))


def _parse_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not hasattr(v, "hour"):
        return v
    return date.fromisoformat(str(v)[:10])
