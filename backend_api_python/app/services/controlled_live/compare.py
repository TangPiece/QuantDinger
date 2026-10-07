"""Phase 7C：Shadow vs Real 成交对比（slippage/qty/fee/latency）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .protocol import ShadowVsRealFinding, ShadowVsRealReport


def compare_shadow_vs_real(
    *,
    order_id: str,
    account_id: str,
    shadow_fill: Mapping[str, Any] | None,
    real_fill: Mapping[str, Any] | None,
    submit_latency_ms: float = 0.0,
) -> ShadowVsRealReport:
    """输出 Δ 报告；不触发补仓或改单。"""
    sh = dict(shadow_fill or {})
    rl = dict(real_fill or {})
    sym = str(rl.get("symbol") or sh.get("symbol") or "").upper()
    sh_qty = float(sh.get("filled_quantity") or sh.get("quantity") or 0)
    rl_qty = float(rl.get("filled_quantity") or rl.get("quantity") or 0)
    sh_px = float(sh.get("avg_fill_price") or sh.get("price") or 0)
    rl_px = float(rl.get("avg_fill_price") or rl.get("price") or 0)
    slippage_bps = 0.0
    if sh_px > 0 and rl_px > 0:
        slippage_bps = (rl_px - sh_px) / sh_px * 10_000.0
    fee_delta = float(rl.get("fee") or 0) - float(sh.get("fee") or 0)
    delta_qty = rl_qty - sh_qty
    sev = "INFO" if abs(delta_qty) < 1e-6 and abs(slippage_bps) < 5 else "WARN"
    finding = ShadowVsRealFinding(
        symbol=sym,
        shadow_qty=sh_qty,
        real_qty=rl_qty,
        qty_delta=delta_qty,
        shadow_avg_price=sh_px,
        real_avg_price=rl_px,
        slippage_bps=slippage_bps,
        fee_delta=fee_delta,
        latency_ms=submit_latency_ms,
        severity=sev,
    )
    return ShadowVsRealReport(
        run_id="clcmp_" + uuid4().hex[:16],
        order_id=order_id,
        account_id=account_id,
        findings=[finding],
        created_at=datetime.now(timezone.utc).isoformat(),
    )
