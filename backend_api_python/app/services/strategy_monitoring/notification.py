"""Phase 8F：NotificationDispatcher — Recording/Fake 通道。"""

from __future__ import annotations

from datetime import datetime, timezone

from .identity import build_dispatch_id
from .protocol import AlertSeverity, NotificationChannel, NotificationDispatch, StrategyAlert


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotificationDispatcher:
    """仅记录 dispatch，禁止真实 sendTelegram / SMTP。"""

    def __init__(self, *, default_channel: NotificationChannel = "RECORDING") -> None:
        self._default_channel = default_channel
        self._dispatches: list[NotificationDispatch] = []

    def dispatch(
        self,
        alert: StrategyAlert,
        *,
        channel: NotificationChannel | None = None,
        session_id: str = "",
    ) -> NotificationDispatch:
        ch = channel or self._default_channel
        if ch not in ("RECORDING", "FAKE"):
            ch = "RECORDING"
        ts = _now()
        record = NotificationDispatch(
            dispatch_id=build_dispatch_id(
                alert_id=alert.alert_id, channel=ch, dispatched_at=ts
            ),
            strategy_code=alert.strategy_code,
            alert_id=alert.alert_id,
            channel=ch,
            severity=alert.severity,
            payload_json={
                "title": alert.title,
                "message": alert.message,
                "occurrence_count": alert.occurrence_count,
            },
            dispatched_at=ts,
            session_id=session_id or alert.session_id,
        )
        self._dispatches.append(record)
        return record

    def list_dispatches(self) -> list[NotificationDispatch]:
        return list(self._dispatches)


__all__ = ["NotificationDispatcher"]
