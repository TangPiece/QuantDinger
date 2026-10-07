"""Phase 7E：账户注册与 Strategy→Account 绑定（策略只能打到绑定账户）。"""

from __future__ import annotations

from .protocol import AccountRegistryEntry, StrategyAccountBind


class AccountBindingError(RuntimeError):
    pass


def assert_strategy_account_bind(
    bind: StrategyAccountBind | None,
    *,
    account_id: str,
    strategy_id: str,
) -> None:
    if bind is None:
        raise AccountBindingError(f"strategy {strategy_id} not bound to any account")
    if bind.strategy_id != strategy_id:
        raise AccountBindingError("strategy_id mismatch on bind")
    if bind.account_id != account_id:
        raise AccountBindingError(
            f"strategy {strategy_id} bound to {bind.account_id}, not {account_id}"
        )


def register_account(
    account_id: str,
    *,
    label: str = "",
    environment: str = "LIVE_CONTROLLED",
) -> AccountRegistryEntry:
    return AccountRegistryEntry(
        account_id=account_id,
        label=label or account_id,
        environment=environment,
    )
