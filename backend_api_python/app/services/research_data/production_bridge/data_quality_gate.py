"""Production Data Quality Gate（P0 → STOP）。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from .protocol import GateResult, ProductionBundleSummary


def run_data_quality_gate(
    summary: ProductionBundleSummary,
    *,
    price_bars: Sequence[Mapping[str, Any]] | None = None,
    factor_rows: Sequence[Mapping[str, Any]] | None = None,
    universe_membership: Sequence[str] | None = None,
    as_of: date | datetime | None = None,
) -> GateResult:
    """检查数据完整性 / 异常 / 未来时间 / NaN / universe / 身份匹配。"""
    details: dict[str, Any] = {}
    failures: list[str] = []

    if not summary.strategy_hash:
        failures.append("missing strategy_hash")
    if not summary.cv_hash:
        failures.append("missing cv_hash")
    if not summary.checksum and not summary.storage_uri:
        failures.append("missing checksum/storage")

    # snapshot / universe 身份（注入场景允许空，但两侧需一致已在 freeze 钉住）
    details["snapshot_id"] = summary.snapshot_id
    details["universe_code"] = summary.universe_code

    now = as_of or datetime.now(timezone.utc)
    if isinstance(now, date) and not isinstance(now, datetime):
        as_of_date = now
    else:
        as_of_date = now.date() if isinstance(now, datetime) else date.today()

    membership = {str(x) for x in (universe_membership or [])}

    if price_bars is not None:
        details["n_bars"] = len(price_bars)
        if len(price_bars) == 0:
            failures.append("empty price_bars")
        for i, r in enumerate(price_bars):
            td = str(r.get("trading_date") or "")[:10]
            if td and td > as_of_date.isoformat():
                failures.append(f"future_bar[{i}]={td}")
                break
            ik = str(r.get("instrument_key") or "")
            if membership and ik and ik not in membership:
                failures.append(f"bar_outside_universe:{ik}")
                break
            for k in ("open", "close"):
                if k not in r:
                    continue
                try:
                    v = float(r[k])
                except (TypeError, ValueError):
                    failures.append(f"bad_price[{i}].{k}")
                    break
                if v != v or v == float("inf") or v == float("-inf"):
                    failures.append(f"nan_inf_price[{i}].{k}")
                    break
                if v <= 0:
                    failures.append(f"non_positive_price[{i}].{k}")
                    break
            else:
                continue
            break

    if factor_rows is not None:
        details["n_factor_rows"] = len(factor_rows)
        for i, r in enumerate(factor_rows):
            raw = r.get("score", r.get("value", r.get("factor_value")))
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                failures.append(f"bad_factor[{i}]")
                break
            if v != v or v == float("inf") or v == float("-inf"):
                failures.append(f"nan_inf_factor[{i}]")
                break

    # processor/model 匹配：若声明了 model 则要求 artifact id
    if summary.model_version and not summary.model_artifact_id:
        failures.append("model_version without model_artifact_id")
    if summary.processor_hash and summary.pipeline_digest == "" and not summary.processor_artifact_uri:
        details["processor_note"] = "processor_hash without digest (allowed)"

    if failures:
        return GateResult(
            gate="data_quality",
            passed=False,
            severity="P0",
            message="; ".join(failures[:8]),
            details=details,
        )
    return GateResult(
        gate="data_quality",
        passed=True,
        message="data quality ok",
        details=details,
    )
