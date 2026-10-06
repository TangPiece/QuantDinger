"""单日 / 单 tick 生命周期编排。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services.research_data.production_bridge.protocol import InferenceRequest

from app.services.research_data.contracts import ProductionRuntimeEventRecord

from .events import make_event_id
from .hash import instrument_fingerprint
from .idempotency import build_idempotency_key, lookup_run, new_run_id
from .market_data import MarketDataProvider, PaperAsOfMarketDataProvider
from .online_feature import OnlineFeatureEngine
from .protocol import RuntimeInstance, RuntimeTickResult, SessionPhase
from .risk_port import FiveFSignalGatePort, RiskGatePort
from .session import MarketSchedule, decision_bucket
from .state_machine import is_tickable
from .writers import ProductionRuntimeWriter


class CycleError(RuntimeError):
    """tick 编排失败。"""


def run_tick(
    instance: RuntimeInstance,
    *,
    bridge: Any,
    writer: ProductionRuntimeWriter,
    registry: Any,
    market_data: MarketDataProvider | None = None,
    feature_engine: OnlineFeatureEngine | None = None,
    risk_port: RiskGatePort | None = None,
    schedule: MarketSchedule | None = None,
    now: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTickResult:
    """执行一次 tick：session → idempotency → data → feature → infer → risk → persist。"""
    meta = dict(metadata or {})
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    schedule = schedule or MarketSchedule()
    risk_port = risk_port or FiveFSignalGatePort()
    feature_engine = feature_engine or OnlineFeatureEngine(
        feature_version=str(meta.get("feature_version") or "online@1"),
        processor_version=str(meta.get("processor_version") or ""),
    )

    if not is_tickable(instance.status):
        return RuntimeTickResult(
            runtime_id=instance.runtime_id,
            run_id="",
            idempotency_key="",
            trading_date=instance.trading_date,
            session_phase=instance.session_phase,
            status="FAILED",
            metadata={"error": f"runtime not tickable: {instance.status}"},
        )

    session = schedule.build_session(
        instance.market,
        now=now,
        trading_date=(
            date.fromisoformat(instance.trading_date)
            if instance.trading_date
            else None
        ),
    )
    # metadata 可覆盖交易日 / 相位（Golden）
    if meta.get("trading_date"):
        td = date.fromisoformat(str(meta["trading_date"])[:10])
        session = session.model_copy(update={"trading_date": td})
    if meta.get("session_phase"):
        session = session.model_copy(update={"phase": meta["session_phase"]})

    trading_date = session.trading_date.isoformat()
    phase: SessionPhase | str = session.phase
    event_types: list[str] = []

    def _emit(etype: str, message: str = "", payload: dict | None = None) -> None:
        # 经 writer 一次性写入 registry + artifact，避免双写
        rec = ProductionRuntimeEventRecord(
            event_id=make_event_id(instance.runtime_id, etype),
            runtime_id=instance.runtime_id,
            event_type=etype,
            trading_date=trading_date,
            session_phase=str(phase),
            message=message,
            payload_json=dict(payload or {}),
            created_at=now.isoformat(),
        )
        event_types.append(etype)
        try:
            writer.write_event(rec)
        except Exception:
            pass

    _emit("SESSION_PHASE", f"phase={phase}")

    # PRE_MARKET：warm only（测试可用 force_intraday 跳过）
    if phase == "PRE_MARKET" and not meta.get("force_intraday"):
        return RuntimeTickResult(
            runtime_id=instance.runtime_id,
            run_id="",
            idempotency_key="",
            trading_date=trading_date,
            session_phase=str(phase),
            status="OK",
            events=event_types,
            metadata={"action": "warm", "bundle_hash": instance.bundle_hash},
        )

    instruments = list(meta.get("instruments") or meta.get("universe_membership") or [])
    bucket = str(meta.get("decision_bucket") or decision_bucket(phase, now))
    ikey = build_idempotency_key(
        bundle_hash=instance.bundle_hash,
        trading_date=trading_date,
        session_phase=str(phase),
        decision_bucket=bucket,
        instruments=instruments,
        signal_version=str(meta.get("signal_version") or ""),
    )

    if not meta.get("force_new_run"):
        existing = lookup_run(registry, ikey)
        if existing is not None:
            return RuntimeTickResult(
                runtime_id=instance.runtime_id,
                run_id=existing.run_id,
                idempotency_key=ikey,
                trading_date=trading_date,
                session_phase=str(phase),
                status="SKIPPED_IDEMPOTENT",
                reused=True,
                bridge_run_id=existing.bridge_run_id,
                events=event_types,
                metadata={
                    "bundle_hash": instance.bundle_hash,
                    "idempotency_key": ikey,
                    "reused_run_id": existing.run_id,
                },
            )

    run_id = new_run_id(ikey)

    # Market data
    mdp = market_data
    if mdp is None:
        mdp = PaperAsOfMarketDataProvider(
            injected=meta.get("price_bars"),
            market=instance.market,
            schedule=schedule,
        )
    start = session.trading_date - timedelta(days=int(meta.get("lookback_days") or 60))
    bars = mdp.bars(
        instruments,
        start,
        session.trading_date,
        as_of=session.trading_date,
    )
    if not bars and not meta.get("price_bars") and not meta.get("factor_rows"):
        _emit("DATA_STALE", "no bars / factor_rows")
        result = RuntimeTickResult(
            runtime_id=instance.runtime_id,
            run_id=run_id,
            idempotency_key=ikey,
            trading_date=trading_date,
            session_phase=str(phase),
            status="FAILED",
            events=event_types,
            metadata={
                "bundle_hash": instance.bundle_hash,
                "error": "DATA_STALE",
                "instrument_fp": instrument_fingerprint(instruments),
            },
        )
        writer.write_run(result)
        return result

    price_bars = list(meta.get("price_bars") or bars)
    _emit("DATA_READY", f"n_bars={len(price_bars)}")

    # Online feature
    factor_rows = list(meta.get("factor_rows") or meta.get("signal_rows") or [])
    if not factor_rows:
        factor_rows = [
            {
                "instrument_key": r.get("instrument_key"),
                "trading_date": str(r.get("trading_date") or "")[:10],
                "score": float(r.get("close") or r.get("open") or 0.0),
            }
            for r in price_bars
            if str(r.get("trading_date") or "")[:10] == trading_date
        ]
    feat = feature_engine.compute(factor_rows, trading_date=trading_date)
    _emit(
        "FEATURE_COMPUTED",
        f"n={feat.metadata.get('n_values', 0)}",
        {"feature_version": feat.feature_version},
    )

    # 5F infer（复用，不重写）
    req = InferenceRequest(
        bundle_hash=instance.bundle_hash,
        trading_date=session.trading_date,
        knowledge_time=now,
        instruments=instruments,
    )
    infer_meta = {
        "factor_rows": feat.rows or factor_rows,
        "price_bars": price_bars,
        "universe_membership": instruments
        or list(meta.get("universe_membership") or []),
        "max_single_weight": float(meta.get("max_single_weight") or 1.0),
        "max_gross_exposure": float(meta.get("max_gross_exposure") or 1.0),
        "current_positions": meta.get("current_positions"),
        "notional": meta.get("notional"),
    }
    resp = bridge.infer(req, metadata=infer_meta)
    _emit("MODEL_INFERRED", f"bridge_run={resp.run_id}", {"status": resp.status})
    _emit("SIGNAL_GENERATED", f"n={len(resp.signals)}")

    gate = risk_port.evaluate(
        resp.signals,
        resp.targets,
        {
            "universe_membership": infer_meta["universe_membership"],
            "max_single_weight": infer_meta["max_single_weight"],
            "max_gross_exposure": infer_meta["max_gross_exposure"],
            "now": now,
        },
    )
    if gate.passed:
        _emit("RISK_PASSED", gate.message)
    else:
        _emit("RISK_REJECTED", gate.message)

    intents = list(resp.order_intents) if gate.passed else []
    tagged = []
    for oi in intents:
        reason = (oi.reason or "") + f"|idem={ikey[:12]}"
        tagged.append(oi.model_copy(update={"reason": reason}))
    if tagged:
        _emit("ORDER_INTENT_CREATED", f"n={len(tagged)}")

    status = "OK"
    if resp.status == "STOPPED" or not gate.passed:
        status = "STOPPED"
    elif resp.status == "FAILED":
        status = "FAILED"

    if phase == "MARKET_CLOSE":
        _emit("SESSION_PHASE", "freeze_decision_window")

    result = RuntimeTickResult(
        runtime_id=instance.runtime_id,
        run_id=run_id,
        idempotency_key=ikey,
        trading_date=trading_date,
        session_phase=str(phase),
        status=status,  # type: ignore[arg-type]
        signals=list(resp.signals),
        targets=list(resp.targets),
        order_intents=tagged,
        gate_results=list(resp.gate_results) + [gate],
        events=event_types,
        bridge_run_id=resp.run_id,
        metadata={
            "bundle_hash": instance.bundle_hash,
            "feature_version": feat.feature_version,
            "processor_version": feat.processor_version,
            "decision_bucket": bucket,
            "idempotency_key": ikey,
        },
    )
    writer.write_run(
        result,
        bridge_payload={
            "run_id": resp.run_id,
            "status": resp.status,
            "feature_version": resp.feature_version,
            "model_version": resp.model_version,
        },
    )
    return result
