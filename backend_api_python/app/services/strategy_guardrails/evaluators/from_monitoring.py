"""Phase 8G：从 8F Monitoring 读取 Health / Alert → BreachSignal。"""

from __future__ import annotations

from typing import Any

from app.services.strategy_monitoring.protocol import StrategyAlert

from ..protocol import BreachSignal


def breaches_from_alerts(alerts: list[StrategyAlert]) -> list[BreachSignal]:
    out: list[BreachSignal] = []
    for alert in alerts:
        if alert.status == "RESOLVED":
            continue
        out.append(
            BreachSignal(
                category=str(alert.category or "SYSTEM").upper(),
                severity=str(alert.severity or "WARNING").upper(),
                metric=str(alert.metadata.get("metric") or alert.rule_id or ""),
                value=float(alert.metadata.get("value") or 0),
                alert_id=alert.alert_id,
                message=alert.message or alert.title,
            )
        )
    return out


def breaches_from_health_overall(
    *,
    strategy_code: str,
    overall: str,
    dimensions: list[Any] | None = None,
) -> list[BreachSignal]:
    """维度 CRITICAL 补充（Performance 等）。"""
    out: list[BreachSignal] = []
    for dim in dimensions or []:
        cat = str(getattr(dim, "category", dim.get("category") if isinstance(dim, dict) else "")).upper()
        st = str(getattr(dim, "status", dim.get("status") if isinstance(dim, dict) else "")).upper()
        if st in ("CRITICAL", "HALTED"):
            out.append(
                BreachSignal(
                    category=cat or "SYSTEM",
                    severity="CRITICAL" if st == "CRITICAL" else "EMERGENCY",
                    message=f"{strategy_code} dimension {cat} {st}",
                )
            )
    if str(overall or "").upper() in ("CRITICAL", "HALTED") and not out:
        out.append(
            BreachSignal(
                category="SYSTEM",
                severity="CRITICAL",
                message=f"{strategy_code} overall {overall}",
            )
        )
    return out


__all__ = ["breaches_from_alerts", "breaches_from_health_overall"]
