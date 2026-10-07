"""Phase 6J：编排 OMS recover_on_start + 可选 Recon。"""

from __future__ import annotations

from typing import Any

from app.services.oms.protocol import RecoverReport


def orchestrate_recover_on_start(
    oms_service: Any,
    *,
    account_id: str = "",
    recon_service: Any = None,
) -> RecoverReport:
    """调用 OMS recover；可选触发 FAST Recon。"""
    report = oms_service.recover_on_start(account_id=account_id)
    if recon_service is not None and account_id:
        try:
            pid = ""
            if hasattr(oms_service, "list_orders"):
                orders = oms_service.list_orders(account_id=account_id)
                if orders:
                    pid = str(orders[0].portfolio_id or "")
            if pid:
                recon_service.run(
                    account_id,
                    pid,
                    mode="FAST",
                    salt=f"recover|{account_id}",
                )
        except Exception as exc:
            report.errors.append(f"recon after recover: {exc}")
    report.resubmit_attempted = False
    return report
