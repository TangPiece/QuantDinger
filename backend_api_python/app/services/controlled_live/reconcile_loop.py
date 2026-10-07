"""Phase 7D：持续 FAST 对账 → CRITICAL 触发 Safety + Session halt。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .protocol import ControlledSession
from .session import halt_session


def run_fast_recon(
    recon: Any | None,
    *,
    account_id: str,
    portfolio_id: str = "",
    inject: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """调用 ReconciliationService.run(FAST)；无 recon 时返回 SKIPPED。"""
    if recon is None:
        return {"status": "SKIPPED", "reason": "no_reconciliation_service"}
    try:
        run = recon.run(
            account_id,
            portfolio_id or account_id,
            mode="FAST",
            inject=inject,
        )
        payload = run.model_dump(mode="json") if hasattr(run, "model_dump") else dict(run)
        return {"status": "OK", "run": payload}
    except Exception as exc:
        return {"status": "ERROR", "reason": str(exc)[:200]}


def critical_from_result(result: Mapping[str, Any]) -> bool:
    """从 run 摘要判断是否存在 CRITICAL。"""
    run = result.get("run") or result
    if not isinstance(run, dict):
        return False
    if int(run.get("critical_count") or 0) > 0:
        return True
    if run.get("gate_blocked"):
        return True
    return str(run.get("status", "")).upper() == "CRITICAL"


def after_submit_or_tick(
    recon: Any | None,
    safety: Any | None,
    session: ControlledSession,
    *,
    portfolio_id: str = "",
    inject: Mapping[str, Any] | None = None,
    ops: Any | None = None,
) -> tuple[ControlledSession, dict[str, Any]]:
    """FAST 对账；CRITICAL → report_source + halt session。"""
    from . import metrics as cl_metrics

    result = run_fast_recon(
        recon,
        account_id=session.account_id,
        portfolio_id=portfolio_id,
        inject=inject,
    )
    if critical_from_result(result):
        if safety is not None:
            try:
                safety.ingest_reconciliation(session.account_id, critical=True)
            except Exception:
                try:
                    safety.report_source(
                        "RECONCILIATION_CRITICAL",
                        "ACCOUNT",
                        session.account_id,
                        severity="CRITICAL",
                    )
                except Exception:
                    pass
        cl_metrics.record_recon_mismatch(ops, account_id=session.account_id)
        session = halt_session(session, stop_reason="recon_mismatch")
    return session, result
