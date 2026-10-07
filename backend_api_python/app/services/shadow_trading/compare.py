"""Phase 7B：Shadow vs Live Readonly 持仓 Δ 对账（只观察）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .protocol import ShadowCompareFinding, ShadowCompareReport, ShadowPosition


def compare_positions(
    *,
    account_id: str,
    shadow_positions: Mapping[str, ShadowPosition] | Sequence[ShadowPosition],
    live_positions: Sequence[Any],
) -> ShadowCompareReport:
    """按 symbol 输出 qty_delta；不触发补仓。"""
    shadow_map: dict[str, float] = {}
    if isinstance(shadow_positions, Mapping):
        for sym, pos in shadow_positions.items():
            shadow_map[str(sym).upper()] = float(getattr(pos, "quantity", pos))
    else:
        for pos in shadow_positions:
            shadow_map[str(pos.symbol).upper()] = float(pos.quantity)

    live_map: dict[str, float] = {}
    for row in live_positions:
        if hasattr(row, "instrument_key") or hasattr(row, "symbol"):
            sym = str(
                getattr(row, "symbol", None)
                or getattr(row, "instrument_key", "")
            ).upper()
            if ":" in sym:
                sym = sym.split(":", 1)[1]
            qty = float(getattr(row, "quantity", 0) or getattr(row, "qty", 0))
        elif isinstance(row, dict):
            sym = str(row.get("symbol") or "").upper()
            qty = float(row.get("qty") or row.get("quantity") or 0)
        else:
            continue
        live_map[sym] = qty

    symbols = sorted(set(shadow_map) | set(live_map))
    findings: list[ShadowCompareFinding] = []
    for sym in symbols:
        sq = shadow_map.get(sym, 0.0)
        lq = live_map.get(sym, 0.0)
        delta = sq - lq
        sev = "INFO" if abs(delta) < 1e-6 else "WARN"
        findings.append(
            ShadowCompareFinding(
                symbol=sym,
                shadow_qty=sq,
                live_qty=lq,
                qty_delta=delta,
                severity=sev,
            )
        )

    return ShadowCompareReport(
        run_id="scmp_" + uuid4().hex[:16],
        account_id=account_id,
        findings=findings,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
