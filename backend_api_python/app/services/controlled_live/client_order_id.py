"""Phase 7C：稳定唯一的 client_order_id 生成。"""

from __future__ import annotations

from datetime import datetime, timezone


def derive_client_order_id(
    *,
    session_id: str,
    seq: int = 1,
    trading_date: str | None = None,
) -> str:
    """格式 QD-{date}-{session_short}-{seq}，供 Alpaca by_client_order_id 查询。"""
    if trading_date:
        day = trading_date.replace("-", "")[:8]
    else:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
    sess = session_id.replace("cls_", "")[:12]
    return f"QD-{day}-{sess}-{seq:03d}"
