"""三层 Kill Switch + EmergencyStop Contract。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .hash import derive_intent_id, scope_key
from .protocol import EmergencyStopIntent, KillSwitch, SafetyScope
from .state_machine import SafetyStateError


class KillSwitchStore:
    """内存 + 可选 repository 持久化。"""

    def __init__(self, repository: Any = None) -> None:
        self._repo = repository
        self._mem: dict[str, KillSwitch] = {}

    def get(self, scope: SafetyScope | str, scope_id: str) -> KillSwitch:
        key = scope_key(str(scope), scope_id)
        if self._repo is not None:
            try:
                return self._repo.get_kill_switch(str(scope), scope_id)
            except KeyError:
                pass
        return self._mem.get(key) or KillSwitch(
            scope=str(scope), scope_id=scope_id  # type: ignore[arg-type]
        )

    def engage(
        self,
        scope: SafetyScope | str,
        scope_id: str,
        *,
        reason: str = "",
        operator: str = "",
    ) -> KillSwitch:
        ks = KillSwitch(
            scope=str(scope),  # type: ignore[arg-type]
            scope_id=scope_id,
            engaged=True,
            reason=reason,
            engaged_at=datetime.now(timezone.utc).isoformat(),
            engaged_by=operator,
        )
        self._persist(ks)
        return ks

    def disengage(
        self,
        scope: SafetyScope | str,
        scope_id: str,
        *,
        operator: str = "",
        acknowledged: bool = False,
    ) -> KillSwitch:
        """GLOBAL 需已 acknowledge（由调用方保证）。"""
        cur = self.get(scope, scope_id)
        if str(scope).upper() == "GLOBAL" and cur.engaged and not acknowledged:
            raise SafetyStateError(
                "GLOBAL kill switch disengage requires acknowledge"
            )
        ks = KillSwitch(
            scope=str(scope),  # type: ignore[arg-type]
            scope_id=scope_id,
            engaged=False,
            reason="disengaged",
            engaged_at=None,
            engaged_by=operator,
        )
        self._persist(ks)
        return ks

    def _persist(self, ks: KillSwitch) -> None:
        self._mem[scope_key(ks.scope, ks.scope_id)] = ks
        if self._repo is not None:
            self._repo.set_kill_switch(ks)


def make_emergency_stop(
    *,
    scope: SafetyScope | str,
    scope_id: str,
    reason: str = "",
    cancel_open_orders: bool = True,
    flatten_all: bool = False,
    salt: str = "",
) -> EmergencyStopIntent:
    """构造 EmergencyStop 意图；flatten_all 仅 Contract，不自动执行。"""
    if flatten_all:
        # P0：允许记录意图，但标记未执行
        pass
    return EmergencyStopIntent(
        intent_id=derive_intent_id(
            scope=str(scope), scope_id=scope_id, salt=salt or "emg"
        ),
        scope=str(scope),  # type: ignore[arg-type]
        scope_id=scope_id,
        stop_new_orders=True,
        cancel_open_orders=cancel_open_orders,
        flatten_all=bool(flatten_all),
        reason=reason,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={"auto_execute_flatten": False},
    )
