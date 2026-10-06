"""ExposureProvider：PIT Size + Industry panel；BETA 需注入否则失败。"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Protocol, Sequence, runtime_checkable

from app.services.research_data.signal.timeutil import resolve_signal_times

from .protocol import ExposureRow, NeutralizationSpec


class ExposureProviderError(RuntimeError):
    """暴露加载失败。"""


def knowledge_time_for(trading_date: date) -> datetime:
    """交易日知识截止（CN 收盘 → UTC）。"""
    _, kt, _ = resolve_signal_times(trading_date)
    return kt


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _as_aware(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


@runtime_checkable
class ExposureProvider(Protocol):
    """按日加载暴露；必须遵守 available_time <= knowledge_time。"""

    def load_for_date(
        self,
        trading_date: date,
        instrument_keys: Sequence[str],
        spec: NeutralizationSpec,
    ) -> list[ExposureRow]: ...


class InjectedExposureProvider:
    """测试 / Golden：从预注入行按日 PIT 过滤。"""

    def __init__(self, rows: Sequence[dict[str, Any] | ExposureRow]) -> None:
        self._rows: list[ExposureRow] = []
        for r in rows:
            if isinstance(r, ExposureRow):
                self._rows.append(r)
            else:
                self._rows.append(
                    ExposureRow(
                        instrument_key=str(r["instrument_key"]),
                        trading_date=_as_date(
                            r.get("trading_date") or r.get("factor_date")
                        ),
                        exposure_code=str(r["exposure_code"]),
                        exposure_value=float(r["exposure_value"]),
                        available_time=_as_aware(r.get("available_time")),
                    )
                )

    def load_for_date(
        self,
        trading_date: date,
        instrument_keys: Sequence[str],
        spec: NeutralizationSpec,
    ) -> list[ExposureRow]:
        """返回当日可用暴露；industry 行用 as-of（available_time <= KT，最近一条）。"""
        kt = knowledge_time_for(trading_date)
        keys = set(instrument_keys)
        needed = set(spec.targets)

        # BETA：无注入则硬失败
        if "BETA" in needed:
            has_beta = any(
                r.exposure_code == "BETA"
                and r.instrument_key in keys
                and (
                    r.available_time is None
                    or r.available_time <= kt
                )
                for r in self._rows
            )
            if not has_beta:
                raise ExposureProviderError(
                    "target BETA requested but no BETA exposure injected; "
                    "Canonical BETA not available in 4G v1"
                )

        out: list[ExposureRow] = []
        # SIZE / BETA：同日精确匹配或 as-of
        for code in ("SIZE", "BETA"):
            if code not in needed:
                continue
            for ik in keys:
                cand = [
                    r
                    for r in self._rows
                    if r.instrument_key == ik
                    and r.exposure_code == code
                    and (r.available_time is None or r.available_time <= kt)
                    and r.trading_date <= trading_date
                ]
                if not cand:
                    continue
                # 最近 available_time，再按 trading_date
                cand.sort(
                    key=lambda r: (
                        r.available_time
                        or datetime.min.replace(tzinfo=timezone.utc),
                        r.trading_date,
                    )
                )
                best = cand[-1]
                val = float(best.exposure_value)
                if code == "SIZE" and spec.size_transform == "LOG":
                    # 约定注入/PIT 的 SIZE 源值为 raw market_cap
                    if val <= 0 or math.isnan(val):
                        continue
                    val = math.log(val)
                out.append(
                    ExposureRow(
                        instrument_key=ik,
                        trading_date=trading_date,
                        exposure_code=code,
                        exposure_value=val,
                        available_time=best.available_time,
                    )
                )

        if "INDUSTRY" in needed:
            for ik in keys:
                cand = [
                    r
                    for r in self._rows
                    if r.instrument_key == ik
                    and r.exposure_code.startswith("INDUSTRY")
                    and (r.available_time is None or r.available_time <= kt)
                    and r.trading_date <= trading_date
                ]
                if not cand:
                    continue
                cand.sort(
                    key=lambda r: (
                        r.available_time
                        or datetime.min.replace(tzinfo=timezone.utc),
                        r.trading_date,
                    )
                )
                best = cand[-1]
                out.append(
                    ExposureRow(
                        instrument_key=ik,
                        trading_date=trading_date,
                        exposure_code=best.exposure_code,
                        exposure_value=float(best.exposure_value),
                        available_time=best.available_time,
                    )
                )
        return out


class CompositeExposureProvider:
    """合并多个 Provider（后者覆盖同 code）。"""

    def __init__(self, providers: Sequence[ExposureProvider]) -> None:
        self._providers = list(providers)

    def load_for_date(
        self,
        trading_date: date,
        instrument_keys: Sequence[str],
        spec: NeutralizationSpec,
    ) -> list[ExposureRow]:
        by_key: dict[tuple[str, str], ExposureRow] = {}
        for p in self._providers:
            for r in p.load_for_date(trading_date, instrument_keys, spec):
                by_key[(r.instrument_key, r.exposure_code)] = r
        return list(by_key.values())
