"""Phase 6I：TradingSession 生命周期。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .hash import derive_session_id
from .modes import assert_mode
from .protocol import E2EMode, TradingSession
from .writers import E2EWriter


def start_session(
    writer: E2EWriter,
    *,
    trading_date: str,
    market: str = "US",
    mode: E2EMode | str = "PAPER",
    dataset_hash: str = "",
    strategy_version: str = "",
    strategy_id: str = "",
    account_id: str = "",
    portfolio_id: str = "",
    salt: str = "",
    metadata: dict[str, Any] | None = None,
) -> TradingSession:
    """打开 E2E Session（幂等 session_id）。"""
    m = assert_mode(mode)
    sid = derive_session_id(
        trading_date=trading_date, market=market, mode=m, salt=salt
    )
    now = datetime.now(timezone.utc).isoformat()
    session = TradingSession(
        session_id=sid,
        trading_date=trading_date,
        market=market,
        mode=m,  # type: ignore[arg-type]
        status="OPEN",
        account_id=account_id,
        portfolio_id=portfolio_id,
        dataset_hash=dataset_hash,
        strategy_version=strategy_version,
        strategy_id=strategy_id,
        opened_at=now,
        metadata=dict(metadata or {}),
    )
    writer.write_session(session)
    return session


def close_session(writer: E2EWriter, session_id: str) -> TradingSession:
    """关闭 Session。"""
    session = writer.get_session(session_id)
    now = datetime.now(timezone.utc).isoformat()
    closed = session.model_copy(update={"status": "CLOSED", "closed_at": now})
    writer.write_session(closed)
    return closed


def attach_scenario_run(
    writer: E2EWriter,
    session_id: str,
    scenario_run_id: str,
) -> TradingSession:
    """将场景运行挂到 Session。"""
    session = writer.get_session(session_id)
    runs = list(session.scenario_run_ids or [])
    if scenario_run_id not in runs:
        runs.append(scenario_run_id)
    updated = session.model_copy(update={"scenario_run_ids": runs})
    writer.write_session(updated)
    return updated
