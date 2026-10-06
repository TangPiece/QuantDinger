"""从 ApplyTargetsResult / 显式参数构建 RiskContext。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.services.portfolio_service.protocol import (
    Account,
    ApplyTargetsResult,
    Position,
    PositionDelta,
)
from app.services.research_data.contracts import Signal, TargetPosition

from .policy import finalize_policy, from_bundle_meta
from .protocol import RiskContext, RiskPolicy


def build_context(
    *,
    apply_result: ApplyTargetsResult | None = None,
    deltas: Sequence[PositionDelta] | None = None,
    account: Account | None = None,
    positions: Sequence[Position] | Mapping[str, Position] | None = None,
    targets: Sequence[TargetPosition] | None = None,
    policy: RiskPolicy | None = None,
    trading_status: Mapping[str, Mapping[str, Any]] | None = None,
    prices: Mapping[str, float] | None = None,
    signals: Sequence[Signal] | None = None,
    knowledge_time: datetime | None = None,
    market_data_as_of: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> RiskContext:
    """组装 RiskContext；优先用 apply_result 字段。"""
    meta = dict(metadata or {})
    pol = finalize_policy(policy or from_bundle_meta(meta))

    acct = account
    pos_map: dict[str, Position] = {}
    dlist: list[PositionDelta] = list(deltas or [])
    tlist: list[TargetPosition] = list(targets or [])
    exposure = None
    trading_date = str(meta.get("trading_date") or "")
    account_id = ""
    portfolio_id = ""
    apply_id = ""
    runtime_id = str(meta.get("runtime_id") or "")
    bundle_hash = str(meta.get("bundle_hash") or "")

    if apply_result is not None:
        acct = acct or apply_result.account
        dlist = dlist or list(apply_result.deltas)
        exposure = apply_result.exposure
        trading_date = trading_date or apply_result.trading_date
        account_id = apply_result.account_id
        portfolio_id = apply_result.portfolio_id
        apply_id = apply_result.apply_id
        runtime_id = runtime_id or str(
            (apply_result.metadata or {}).get("runtime_id") or ""
        )
        if apply_result.positions:
            for p in apply_result.positions:
                pos_map[p.instrument_key] = p

    if positions is not None:
        if isinstance(positions, dict):
            pos_map = dict(positions)
        else:
            pos_map = {p.instrument_key: p for p in positions}

    if acct is not None:
        account_id = account_id or acct.account_id

    equity = 0.0
    if acct is not None:
        equity = float(acct.equity) or (
            float(acct.cash.cash) + float(acct.market_value)
        )

    from app.services.portfolio_service.protocol import Exposure

    return RiskContext(
        account=acct,
        positions=pos_map,
        targets=tlist,
        deltas=dlist,
        exposure=exposure or Exposure(),
        prices=dict(prices or meta.get("prices") or {}),
        trading_status={k: dict(v) for k, v in (trading_status or {}).items()},
        signals=list(signals or []),
        knowledge_time=knowledge_time or datetime.now(timezone.utc),
        market_data_as_of=market_data_as_of,
        trading_date=trading_date,
        account_id=account_id,
        portfolio_id=portfolio_id,
        apply_id=apply_id,
        runtime_id=runtime_id,
        bundle_hash=bundle_hash,
        policy=pol,
        equity=equity,
        metadata=meta,
    )
