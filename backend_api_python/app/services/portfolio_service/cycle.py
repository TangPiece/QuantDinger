"""apply_targets 编排：delta → paper_fill → reduce → snapshot。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.services.research_data.contracts import TargetPosition

from .corporate_action import CorporateActionApplier
from .delta import compute_position_deltas
from .exposure import compute_exposure
from .hash import (
    compute_apply_idempotency_key,
    derive_apply_id,
    targets_fingerprint,
)
from .paper_fill import PaperFillSimulator
from .pnl import mark_to_market
from .protocol import (
    ApplyMode,
    ApplyTargetsResult,
    PortfolioState,
)
from .reducer import apply_events, assert_invariants
from .snapshot import build_snapshot
from .writers import PortfolioWriter


def run_apply_targets(
    state: PortfolioState,
    targets: Sequence[TargetPosition],
    *,
    writer: PortfolioWriter,
    registry: Any,
    prices: Mapping[str, float],
    trading_date: str,
    runtime_id: str = "",
    run_id: str = "",
    apply_mode: ApplyMode = "PAPER_FILL",
    corporate_actions: Sequence[Any] | None = None,
    metadata: dict[str, Any] | None = None,
    fill_sim: PaperFillSimulator | None = None,
) -> ApplyTargetsResult:
    """单次 apply：幂等 → delta → fill(可选) → reduce → MTM → snapshot。"""
    meta = dict(metadata or {})
    fp = targets_fingerprint(targets)
    ikey = compute_apply_idempotency_key(
        account_id=state.account.account_id,
        portfolio_id=state.portfolio.portfolio_id,
        trading_date=trading_date,
        runtime_id=runtime_id,
        run_id=run_id,
        targets_fingerprint=fp,
    )
    if not meta.get("force_new_apply"):
        getter = getattr(registry, "get_apply_by_idempotency", None)
        if getter is not None:
            try:
                existing = getter(ikey)
                return ApplyTargetsResult(
                    apply_id=existing.apply_id,
                    account_id=state.account.account_id,
                    portfolio_id=state.portfolio.portfolio_id,
                    snapshot_id=existing.snapshot_id,
                    idempotency_key=ikey,
                    trading_date=trading_date,
                    status="SKIPPED_IDEMPOTENT",
                    reused=True,
                    apply_mode=apply_mode,
                    metadata={
                        "runtime_id": runtime_id,
                        "run_id": run_id,
                        "reused_apply_id": existing.apply_id,
                    },
                )
            except KeyError:
                pass

    apply_id = derive_apply_id(ikey)
    equity = float(state.account.equity) or (
        float(state.account.cash.cash) + float(state.account.market_value)
    )
    # 先用价格估 market_value 以便算权重
    mark_to_market(state, prices)
    equity = float(state.account.equity)

    deltas = compute_position_deltas(
        targets, state.positions, equity=equity, prices=prices
    )

    events = []
    # CA 先于成交
    if corporate_actions:
        ca_events = CorporateActionApplier().apply(state, corporate_actions)
        if ca_events:
            apply_events(state, ca_events)
            events.extend(ca_events)
            for ev in ca_events:
                writer.write_event(ev)

    if apply_mode == "PAPER_FILL":
        sim = fill_sim or PaperFillSimulator()
        fill_events = sim.fill(
            state,
            deltas,
            prices,
            trading_date=trading_date,
            idempotency_key=ikey,
        )
        apply_events(state, fill_events)
        events.extend(fill_events)
        for ev in fill_events:
            writer.write_event(ev)
    # SHADOW_DRY：只算 delta，不写成交

    mark_to_market(state, prices)
    assert_invariants(state)
    exp = compute_exposure(state.positions, equity=float(state.account.equity))
    state.account = state.account.model_copy(update={"exposure": exp}).recompute_equity()

    turnover = sum(abs(float(d.notional)) for d in deltas)
    snap = build_snapshot(
        state,
        trading_date=trading_date,
        knowledge_time=datetime.now(timezone.utc).isoformat(),
        runtime_id=runtime_id,
        bundle_hash=state.portfolio.bundle_hash,
        turnover=turnover,
        metadata={"apply_id": apply_id, "apply_mode": apply_mode},
    )
    written = writer.write_snapshot(snap, idempotency_key=ikey)
    snap = snap.model_copy(update={"storage_uri": written.storage_uri})

    state.portfolio = state.portfolio.model_copy(update={"trading_date": trading_date})
    writer.persist_state(state)

    result = ApplyTargetsResult(
        apply_id=apply_id,
        account_id=state.account.account_id,
        portfolio_id=state.portfolio.portfolio_id,
        snapshot_id=snap.snapshot_id,
        idempotency_key=ikey,
        trading_date=trading_date,
        status="OK",
        apply_mode=apply_mode,
        deltas=list(deltas),
        events=list(events),
        snapshot=snap,
        pnl=state.account.pnl,
        exposure=exp,
        account=state.account,
        positions=list(state.positions.values()),
        metadata={
            "runtime_id": runtime_id,
            "run_id": run_id,
            "account_id": state.account.account_id,
            "portfolio_id": state.portfolio.portfolio_id,
            "snapshot_id": snap.snapshot_id,
        },
    )
    writer.write_apply(result)
    return result
