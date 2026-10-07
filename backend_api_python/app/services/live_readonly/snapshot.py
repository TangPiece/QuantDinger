"""Phase 7A：LiveReadonlyAdapter → BrokerSnapshot（6F 对账输入）。"""

from __future__ import annotations

from typing import Any, Optional

from app.services.reconciliation_service.protocol import BrokerSnapshot
from app.services.reconciliation_service.snapshot import build_broker_snapshot


def capture_broker_snapshot(
    adapter: Any,
    *,
    account_id: str,
    salt: str = "",
    raw_storage_uri: str = "",
) -> BrokerSnapshot:
    """封装 6F build_broker_snapshot；只读采集。"""
    return build_broker_snapshot(
        adapter,
        account_id=account_id,
        broker_id=str(getattr(adapter, "broker_id", "") or "alpaca_live_readonly"),
        inject=None,
        raw_storage_uri=raw_storage_uri,
        salt=salt,
    )
