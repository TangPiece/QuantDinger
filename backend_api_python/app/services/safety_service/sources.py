"""外部源适配：Recon / Broker / MarketData / StrategyError / Health。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MarketDataFreshnessPort(Protocol):
    """行情新鲜度；返回 age_sec（越大越陈旧）。"""

    def age_sec(self, instrument_key: str) -> float: ...


@runtime_checkable
class BrokerConnectivityPort(Protocol):
    """Broker 连接状态。"""

    def is_connected(self) -> bool: ...


class InMemoryMarketDataFreshness:
    """测试/注入用行情年龄。"""

    def __init__(self, ages: dict[str, float] | None = None) -> None:
        self._ages = dict(ages or {})

    def set_age(self, instrument_key: str, age_sec: float) -> None:
        self._ages[instrument_key] = float(age_sec)

    def age_sec(self, instrument_key: str) -> float:
        return float(self._ages.get(instrument_key, 0.0))


class InMemoryBrokerConnectivity:
    """测试/注入用连接状态。"""

    def __init__(self, connected: bool = True) -> None:
        self._connected = connected

    def set_connected(self, connected: bool) -> None:
        self._connected = bool(connected)

    def is_connected(self) -> bool:
        return self._connected


class SourceFlags:
    """进程内源标志（也由 report_source 写入并持久化到 state metadata）。"""

    def __init__(self) -> None:
        self.recon_critical_accounts: set[str] = set()
        self.strategy_error_counts: dict[str, int] = {}
        self.system_healthy: bool = True
        self.state_known: bool = True

    def set_recon_critical(self, account_id: str, critical: bool) -> None:
        if critical:
            self.recon_critical_accounts.add(account_id)
        else:
            self.recon_critical_accounts.discard(account_id)

    def bump_strategy_error(self, strategy_id: str) -> int:
        n = int(self.strategy_error_counts.get(strategy_id) or 0) + 1
        self.strategy_error_counts[strategy_id] = n
        return n

    def reset_strategy_error(self, strategy_id: str) -> None:
        self.strategy_error_counts[strategy_id] = 0
