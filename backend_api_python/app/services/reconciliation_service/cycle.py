"""run_fast / run_slow / run_eod：采集 Snapshot → compare → Findings → Gate。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from uuid import uuid4

from .compare_cash import compare_cash
from .compare_fills import compare_fills
from .compare_orders import compare_orders
from .compare_pnl import compare_pnl
from .compare_positions import compare_positions
from .cursor import CursorStore
from .gate import TradingGate
from .hash import derive_run_id
from .protocol import ENGINE_VERSION, ReconciliationFinding, ReconciliationRun, RunMode
from .snapshot import build_broker_snapshot
from .writers import ReconciliationWriter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_oms_fills(oms_service: Any, orders: list) -> list:
    fills = []
    for o in orders:
        try:
            fills.extend(list(oms_service.list_fills(o.order_id) or []))
        except Exception:
            continue
    return fills


def run_reconciliation(
    *,
    account_id: str,
    portfolio_id: str,
    mode: RunMode = "FAST",
    writer: ReconciliationWriter,
    gate: TradingGate,
    cursor_store: CursorStore,
    portfolio_service: Any,
    oms_service: Any,
    broker_adapter: Any,
    inject: Mapping[str, Any] | None = None,
    salt: str = "",
) -> tuple[ReconciliationRun, list[ReconciliationFinding]]:
    """执行一次对账；观察者，不改 OMS 持仓。"""
    started = _now()
    run_salt = salt or str(uuid4())[:12]
    run_id = derive_run_id(account_id, mode=mode, salt=run_salt)
    broker_id = str(getattr(broker_adapter, "broker_id", "") or "unknown")
    inj = dict(inject or {})

    # Snapshot
    snap = build_broker_snapshot(
        broker_adapter,
        account_id=account_id,
        broker_id=broker_id,
        inject=inj,
        salt=run_salt,
    )
    writer.write_snapshot(snap)

    # Internal state
    account = portfolio_service.get_account(account_id)
    positions = portfolio_service.get_positions(portfolio_id)
    pos_map = {p.instrument_key: p for p in positions}
    oms_orders = list(oms_service.list_orders(account_id=account_id) or [])

    # FAST：仅 cursor 之后；EOD/SLOW 全量（orders 全量；fills 按 cursor 过滤）
    exec_cursor = cursor_store.get(
        account_id, broker_id=broker_id, cursor_type="EXECUTION"
    )
    oms_fills = _collect_oms_fills(oms_service, oms_orders)
    if mode == "FAST" and exec_cursor.cursor_value:
        # cursor_value = 上次最大 broker_execution_id 序号启发式：字符串比较
        cv = exec_cursor.cursor_value
        filtered = []
        for f in oms_fills:
            meta = dict(getattr(f, "metadata", None) or {})
            eid = str(meta.get("broker_execution_id") or getattr(f, "fill_id", ""))
            if eid > cv:
                filtered.append(f)
        oms_fills = filtered
        # Snapshot executions 同样过滤
        snap = snap.model_copy(
            update={
                "executions": [
                    e for e in snap.executions if str(e.broker_execution_id) > cv
                ]
            }
        )

    findings: list[ReconciliationFinding] = []
    findings.extend(
        compare_orders(run_id=run_id, oms_orders=oms_orders, snapshot=snap)
    )
    findings.extend(
        compare_fills(run_id=run_id, oms_fills=oms_fills, snapshot=snap)
    )
    findings.extend(
        compare_positions(
            run_id=run_id, account=account, positions=pos_map, snapshot=snap
        )
    )
    findings.extend(
        compare_cash(run_id=run_id, account=account, snapshot=snap)
    )
    findings.extend(
        compare_pnl(
            run_id=run_id,
            account=account,
            snapshot=snap,
            metadata=inj.get("pnl") if isinstance(inj.get("pnl"), dict) else inj,
        )
    )

    # 打上 account_id 便于 Gate 清除与 list 过滤
    stamped: list[ReconciliationFinding] = []
    for f in findings:
        meta = dict(f.metadata or {})
        meta["account_id"] = account_id
        stamped.append(f.model_copy(update={"metadata": meta}))
    findings = stamped

    for f in findings:
        writer.write_finding(f)

    gate_state = gate.apply_findings(account_id, findings)
    # CRITICAL → 6B RECONCILIATION_REQUIRED
    if gate_state.blocked and hasattr(portfolio_service, "reconcile"):
        try:
            from app.services.portfolio_service.reconciliation import (
                mark_reconciliation_required,
            )

            acct = portfolio_service.get_account(account_id)
            if str(acct.status) != "RECONCILIATION_REQUIRED":
                marked = mark_reconciliation_required(acct)
                # 经 writer 写回
                w = getattr(portfolio_service, "_writer", None)
                if w is not None:
                    w.write_account(marked)
        except Exception:
            pass

    # 更新 cursor（取最大 execution id）
    max_eid = exec_cursor.cursor_value
    for e in snap.executions:
        if str(e.broker_execution_id) > (max_eid or ""):
            max_eid = str(e.broker_execution_id)
    for f in oms_fills:
        meta = dict(getattr(f, "metadata", None) or {})
        eid = str(meta.get("broker_execution_id") or "")
        if eid > (max_eid or ""):
            max_eid = eid
    if max_eid:
        cursor_store.set(
            account_id,
            broker_id=broker_id,
            cursor_type="EXECUTION",
            cursor_value=max_eid,
        )
    cursor_store.set(
        account_id,
        broker_id=broker_id,
        cursor_type="SNAPSHOT_TIME",
        cursor_value=snap.captured_at,
    )

    crit = sum(1 for f in findings if f.severity == "CRITICAL")
    info = sum(1 for f in findings if f.severity == "INFO")
    warn = sum(1 for f in findings if f.severity == "WARNING")
    err = sum(1 for f in findings if f.severity == "ERROR")
    run = ReconciliationRun(
        run_id=run_id,
        account_id=account_id,
        portfolio_id=portfolio_id,
        broker_id=broker_id,
        mode=mode,
        started_at=started,
        completed_at=_now(),
        snapshot_id=snap.snapshot_id,
        finding_count=len(findings),
        critical_count=crit,
        info_count=info,
        warning_count=warn,
        error_count=err,
        gate_blocked=bool(gate_state.blocked),
        engine_version=ENGINE_VERSION,
        metadata={"inject_keys": list(inj.keys())},
    )
    writer.write_run(run)
    return run, findings


def run_fast(**kwargs: Any) -> tuple[ReconciliationRun, list[ReconciliationFinding]]:
    return run_reconciliation(mode="FAST", **kwargs)


def run_slow(**kwargs: Any) -> tuple[ReconciliationRun, list[ReconciliationFinding]]:
    return run_reconciliation(mode="SLOW", **kwargs)


def run_eod(**kwargs: Any) -> tuple[ReconciliationRun, list[ReconciliationFinding]]:
    return run_reconciliation(mode="EOD", **kwargs)
