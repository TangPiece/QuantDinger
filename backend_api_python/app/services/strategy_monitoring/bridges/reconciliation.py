"""Phase 8F：只读 Reconciliation inject / 摘要。"""

from __future__ import annotations

from typing import Any, Mapping


def load_reconciliation_inject(
    reconciliation: Any | None,
    *,
    strategy_code: str,
    inject_section: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """P0：优先 Fake inject；服务桥接留空壳。"""
    if inject_section:
        return dict(inject_section)
    _ = reconciliation, strategy_code
    return {}


def reconciliation_view(section: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "critical_finding_count": float(
            section.get("critical_finding_count") or section.get("critical_findings") or 0
        ),
        "severity": str(section.get("severity") or section.get("overall_severity") or "OK"),
    }


__all__ = ["load_reconciliation_inject", "reconciliation_view"]
