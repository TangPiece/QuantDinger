"""Phase 7B/7C：OrderExecutionGateway — 仅 LIVE_CONTROLLED 允许 real submit。"""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.services.oms.protocol import Order


class EnvironmentViolation(RuntimeError):
    """当前 TradingEnvironment 不允许真实 Broker 写操作。"""


_REAL_ENV_BLOCK = frozenset({"SHADOW", "LIVE_READONLY", "PAPER"})
_LIVE_FORBIDDEN = frozenset({"LIVE"})


def is_real_broker(broker_port: Any) -> bool:
    """识别 Alpaca Live / 生产 trading host（只读 adapter 不算 real submit 目标）。"""
    bid = str(getattr(broker_port, "broker_id", "") or "").lower()
    if "readonly" in bid:
        return False
    if bid in ("simulated", "alpaca_paper", "paper"):
        return False
    if "paper" in bid or "sandbox" in bid:
        return False
    if "controlled_fake" in bid:
        return True
    if bid.startswith("alpaca_live") or bid == "alpaca_live":
        return True

    tr = getattr(broker_port, "_transport", None)
    base = str(
        getattr(tr, "base_url", "")
        or getattr(broker_port, "base_url", "")
        or ""
    ).lower()
    if "api.alpaca.markets" in base and "paper" not in base:
        return True
    mode = str(getattr(broker_port, "execution_mode", "") or "").upper()
    if mode in ("LIVE", "LIVE_CONTROLLED"):
        return True
    return False


class OrderExecutionGateway:
    """唯一允许触达 BrokerPort.submit 的门。"""

    def submit_real(
        self,
        environment: str,
        order: Order,
        broker_port: Any,
        *,
        submit_fn: Optional[Callable[[Order], Any]] = None,
    ) -> Any:
        env = str(environment or "PAPER").strip().upper()
        if env in _LIVE_FORBIDDEN:
            raise EnvironmentViolation("LIVE forbidden")
        if env == "LIVE_CONTROLLED":
            if submit_fn is None:
                raise EnvironmentViolation("submit_fn required for LIVE_CONTROLLED")
            return submit_fn(order)
        if env in _REAL_ENV_BLOCK and is_real_broker(broker_port):
            raise EnvironmentViolation("REAL_BROKER_ORDER denied")
        if submit_fn is None:
            raise EnvironmentViolation("submit_fn required for allowed paths")
        return submit_fn(order)

    def cancel_real(self, environment: str, broker_port: Any, **kwargs: Any) -> Any:
        env = str(environment or "PAPER").strip().upper()
        if env in _LIVE_FORBIDDEN:
            raise EnvironmentViolation("LIVE forbidden")
        if env == "LIVE_CONTROLLED":
            raise EnvironmentViolation("REAL_BROKER_CANCEL denied for LIVE_CONTROLLED")
        if env in _REAL_ENV_BLOCK and is_real_broker(broker_port):
            raise EnvironmentViolation("REAL_BROKER_CANCEL denied")
        raise EnvironmentViolation("cancel_real not implemented in Phase 7B")

    def replace_real(self, environment: str, broker_port: Any, **kwargs: Any) -> Any:
        env = str(environment or "PAPER").strip().upper()
        if env in _LIVE_FORBIDDEN:
            raise EnvironmentViolation("LIVE forbidden")
        if env == "LIVE_CONTROLLED":
            raise EnvironmentViolation("REAL_BROKER_REPLACE denied for LIVE_CONTROLLED")
        if env in _REAL_ENV_BLOCK and is_real_broker(broker_port):
            raise EnvironmentViolation("REAL_BROKER_REPLACE denied")
        raise EnvironmentViolation("replace_real not implemented in Phase 7B")
