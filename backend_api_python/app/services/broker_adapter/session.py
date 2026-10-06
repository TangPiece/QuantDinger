"""BrokerSession connect/disconnect/health。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .errors import AdapterErrorCode, BrokerAdapterError
from .protocol import BrokerAdapter, BrokerSession
from .writers import BrokerWriter


class SessionManager:
    """管理 Adapter 会话生命周期。"""

    def __init__(self, writer: BrokerWriter) -> None:
        self._writer = writer
        self._session: BrokerSession | None = None

    @property
    def session(self) -> BrokerSession | None:
        return self._session

    def connect(self, adapter: BrokerAdapter) -> BrokerSession:
        mode = str(adapter.execution_mode)
        if mode.upper() == "LIVE":
            raise BrokerAdapterError(
                "LIVE not enabled in Phase 6E",
                code=AdapterErrorCode.LIVE_FORBIDDEN,
            )
        adapter.connect()
        self._session = self._writer.new_session(
            adapter.broker_id, execution_mode=mode
        )
        return self._session

    def disconnect(self, adapter: BrokerAdapter) -> None:
        adapter.disconnect()
        if self._session is not None:
            sess = self._session.model_copy(
                update={
                    "status": "DISCONNECTED",
                    "created_at": self._session.created_at
                    or datetime.now(timezone.utc).isoformat(),
                }
            )
            self._writer.write_session(sess)
            self._session = sess

    def health(self, adapter: BrokerAdapter) -> dict[str, Any]:
        return {
            "broker_id": adapter.broker_id,
            "execution_mode": adapter.execution_mode,
            "session_status": (
                self._session.status if self._session else "DISCONNECTED"
            ),
            "capabilities": adapter.capabilities.model_dump(mode="json"),
        }
