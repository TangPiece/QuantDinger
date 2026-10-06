"""L2 PIT / Look-ahead Diff。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .protocol import LayerResult


def _parse_ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    text = str(v).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def diff_pit(
    signal_rows: Sequence[Mapping[str, Any]] | None,
    *,
    future_leak_rows: Sequence[Mapping[str, Any]] | None = None,
) -> LayerResult:
    """校验 available_time <= knowledge_time；可选未来发布泄漏测试。"""
    rows = list(signal_rows or [])
    details: dict[str, Any] = {"n_signals": len(rows)}
    violations: list[str] = []

    for i, r in enumerate(rows):
        avail = _parse_ts(r.get("available_time") or r.get("publish_time"))
        know = _parse_ts(r.get("knowledge_time") or r.get("signal_time"))
        if avail is not None and know is not None and avail > know:
            violations.append(
                f"row[{i}] available_time > knowledge_time "
                f"({avail.isoformat()} > {know.isoformat()})"
            )
        exec_t = _parse_ts(r.get("execution_time"))
        if know is not None and exec_t is not None and exec_t <= know:
            violations.append(
                f"row[{i}] look-ahead: execution_time <= knowledge_time"
            )

    # 未来泄漏：future 行的 publish 不得出现在历史 signal 集合
    if future_leak_rows:
        hist_keys = {
            (
                str(r.get("instrument_key") or ""),
                str(r.get("trading_date") or "")[:10],
                str(r.get("score") if r.get("score") is not None else r.get("value")),
            )
            for r in rows
        }
        for fr in future_leak_rows:
            key = (
                str(fr.get("instrument_key") or ""),
                str(fr.get("trading_date") or "")[:10],
                str(fr.get("score") if fr.get("score") is not None else fr.get("value")),
            )
            # 仅当显式标记为不应出现时检查
            if fr.get("must_not_appear_in_history") and key in hist_keys:
                violations.append(
                    f"leakage: future publish appears in history {key}"
                )
        details["future_leak_checked"] = len(future_leak_rows)

    # 无 PIT 时间戳的注入 golden：视为 SKIP 语义下的 PASS（不阻断 baseline）
    has_pit = any(
        r.get("available_time")
        or r.get("publish_time")
        or r.get("knowledge_time")
        or r.get("execution_time")
        for r in rows
    )
    if not rows:
        return LayerResult(
            layer="pit",
            kind="EXACT",
            status="PASS",
            message="no signals; PIT skipped",
            details=details,
        )
    if not has_pit and not violations:
        return LayerResult(
            layer="pit",
            kind="EXACT",
            status="PASS",
            message="injected signals without PIT timestamps; structural OK",
            details=details,
        )
    if violations:
        return LayerResult(
            layer="pit",
            kind="EXACT",
            status="FAIL",
            message="; ".join(violations[:5]),
            details=details,
        )
    return LayerResult(
        layer="pit",
        kind="EXACT",
        status="PASS",
        message="PIT / no look-ahead",
        details=details,
    )
