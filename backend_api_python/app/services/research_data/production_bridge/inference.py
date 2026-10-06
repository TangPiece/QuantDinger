"""干跑 Inference：Load Bundle → Gates → Signal → TargetPosition → OrderIntent。"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from typing import Any, Mapping, Sequence

from app.services.research_data.contracts import (
    OrderIntent,
    ProductionBundleSummary,
    Signal,
    TargetPosition,
)
from app.services.research_data.signal.order_intent_mapper import (
    order_intents_from_targets,
)
from app.services.research_data.signal.timeutil import resolve_signal_times

from .data_quality_gate import run_data_quality_gate
from .integrity import verify_bundle_integrity
from .protocol import GateResult, InferenceRequest, InferenceResponse
from .signal_gate import run_signal_gate


class InferenceError(RuntimeError):
    """推理失败。"""


def run_inference(
    summary: ProductionBundleSummary,
    request: InferenceRequest,
    *,
    factor_rows: Sequence[Mapping[str, Any]] | None = None,
    price_bars: Sequence[Mapping[str, Any]] | None = None,
    universe_membership: Sequence[str] | None = None,
    current_positions: Mapping[str, float] | None = None,
    notional: float = 1_000_000.0,
    max_single_weight: float = 1.0,
    max_gross_exposure: float = 1.0,
) -> InferenceResponse:
    """因子主路径：注入/冻结 score → Signal → Target → OrderIntent（不发单）。"""
    run_id = uuid.uuid4().hex
    td = request.trading_date
    gates: list[GateResult] = []

    g_int = verify_bundle_integrity(summary)
    gates.append(g_int)
    g_dq = run_data_quality_gate(
        summary,
        price_bars=price_bars,
        factor_rows=factor_rows,
        universe_membership=universe_membership,
        as_of=td,
    )
    gates.append(g_dq)

    if not g_int.passed or not g_dq.passed:
        return InferenceResponse(
            run_id=run_id,
            bundle_hash=summary.bundle_hash,
            trading_date=td.isoformat(),
            status="STOPPED",
            gate_results=gates,
            strategy_version=summary.strategy_hash[:16],
            model_version=summary.model_version,
            inference_timestamp=_utc_now(),
            metadata={"stop_reason": "P0_gate"},
        )

    # 仅 APPROVED / DEPLOYED / PAUSED 允许推理（PAUSED 可干跑审计）
    if summary.status not in ("APPROVED", "DEPLOYED", "PAUSED"):
        return InferenceResponse(
            run_id=run_id,
            bundle_hash=summary.bundle_hash,
            trading_date=td.isoformat(),
            status="FAILED",
            gate_results=gates
            + [
                GateResult(
                    gate="status",
                    passed=False,
                    message=f"status {summary.status} not inferable",
                )
            ],
            inference_timestamp=_utc_now(),
        )

    rows = list(factor_rows or [])
    # 过滤交易日
    day_rows = [
        r
        for r in rows
        if str(r.get("trading_date") or "")[:10] == td.isoformat()
    ]
    if request.instruments:
        allow = {str(x) for x in request.instruments}
        day_rows = [
            r
            for r in day_rows
            if str(r.get("instrument_key") or r.get("instrument") or "") in allow
        ]

    signal_time, knowledge_time, execution_time = resolve_signal_times(td)
    if request.knowledge_time is not None:
        knowledge_time = request.knowledge_time
        if knowledge_time.tzinfo is None:
            knowledge_time = knowledge_time.replace(tzinfo=timezone.utc)
        signal_time = knowledge_time

    signals: list[Signal] = []
    weights: dict[str, float] = {}
    # 等权多头：score>0；或使用注入 target_weight
    positive = [
        r
        for r in day_rows
        if _score(r) is not None and float(_score(r) or 0) > 0  # type: ignore[arg-type]
    ]
    n_pos = len(positive) or 1
    for r in day_rows:
        ik = str(r.get("instrument_key") or r.get("instrument") or "")
        sc = _score(r)
        if sc is None:
            continue
        tw = r.get("target_weight")
        if tw is not None:
            w = float(tw)
        elif float(sc) > 0:
            w = 1.0 / n_pos
        else:
            w = 0.0
        if w <= 0:
            continue
        sid = f"{summary.bundle_hash[:8]}_{ik}_{td.isoformat()}"
        signals.append(
            Signal(
                signal_id=sid,
                instrument_key=ik,
                trading_date=td.isoformat(),
                direction="LONG",
                score=float(sc),
                signal_time=signal_time,
                knowledge_time=knowledge_time,
                execution_time=execution_time,
                target_weight=w,
                strategy_version=summary.strategy_hash[:16],
                model_version=summary.model_version,
                dataset_hash=summary.dataset_hash,
                bundle_hash=summary.bundle_hash,
            )
        )
        weights[ik] = w

    ts = datetime.combine(td, time(15, 0, 0), tzinfo=timezone.utc)
    targets = [
        TargetPosition(
            instrument_key=ik,
            trading_date=td.isoformat(),
            portfolio_id=summary.strategy_code or summary.bundle_hash[:16],
            strategy_version=summary.strategy_hash[:16],
            dataset_hash=summary.dataset_hash or summary.strategy_hash,
            timestamp=ts,
            target_weight=w,
            signal_id=f"{summary.bundle_hash[:8]}_{ik}_{td.isoformat()}",
        )
        for ik, w in weights.items()
    ]

    g_sig = run_signal_gate(
        signals,
        targets,
        universe_membership=universe_membership,
        max_single_weight=max_single_weight,
        max_gross_exposure=max_gross_exposure,
        prev_weights=current_positions,
        now=knowledge_time,
    )
    gates.append(g_sig)
    if not g_sig.passed:
        return InferenceResponse(
            run_id=run_id,
            bundle_hash=summary.bundle_hash,
            trading_date=td.isoformat(),
            status="STOPPED",
            signals=signals,
            targets=targets,
            gate_results=gates,
            strategy_version=summary.strategy_hash[:16],
            model_version=summary.model_version,
            inference_timestamp=_utc_now(),
            metadata={"stop_reason": "signal_gate"},
        )

    # 空仓相对：占位 OrderIntent（研究契约）；有 current_positions 时仍用 mapper 简化
    intents: list[OrderIntent] = order_intents_from_targets(
        targets, notional=notional
    )
    # 确保不下单标记
    for it in intents:
        if it.reason is None:
            it.reason = "DRY_RUN_PRODUCTION_BRIDGE"

    return InferenceResponse(
        run_id=run_id,
        bundle_hash=summary.bundle_hash,
        trading_date=td.isoformat(),
        status="OK",
        signals=signals,
        targets=targets,
        order_intents=intents,
        gate_results=gates,
        feature_version=",".join(summary.feature_hashes[:3]),
        model_version=summary.model_version,
        strategy_version=summary.strategy_hash[:16],
        inference_timestamp=_utc_now(),
        metadata={"dry_run": True, "n_weights": len(weights)},
    )


def _score(r: Mapping[str, Any]) -> float | None:
    for k in ("score", "value", "factor_value"):
        if k in r and r[k] is not None:
            try:
                return float(r[k])
            except (TypeError, ValueError):
                return None
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
