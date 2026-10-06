"""合并规则结果 → RiskDecision；只减不增裁剪 deltas。"""

from __future__ import annotations

from typing import Sequence

from app.services.portfolio_service.protocol import PositionDelta

from .protocol import RiskContext, RiskDecision, RiskResult, RiskViolation
from .state_machine import is_blocking, merge_verdicts


def _clip_weight(original_target: float, adjusted: float) -> float:
    """只减不增：同号时 |adj| <= |orig|；异号不允许越过 0 加大反向。"""
    if original_target >= 0:
        return max(0.0, min(float(adjusted), float(original_target)))
    return min(0.0, max(float(adjusted), float(original_target)))


def apply_modifications(
    deltas: Sequence[PositionDelta],
    results: Sequence[RiskResult],
    *,
    equity: float,
    prices: dict[str, float],
) -> list[PositionDelta]:
    """按 MODIFY 结果裁剪目标权重/数量，重算 delta（只减不增）。"""
    # instrument → 建议 target_weight（取最保守：绝对值最小）
    adj_w: dict[str, float] = {}
    for r in results:
        if r.decision not in ("MODIFY", "ALLOW_REDUCE"):
            continue
        if not r.instrument_key or r.adjusted_target_weight is None:
            continue
        key = r.instrument_key
        if key not in adj_w:
            adj_w[key] = float(r.adjusted_target_weight)
        else:
            # 取更接近 0 的（更保守）
            if abs(float(r.adjusted_target_weight)) < abs(adj_w[key]):
                adj_w[key] = float(r.adjusted_target_weight)

    out: list[PositionDelta] = []
    eq = max(float(equity), 0.0)
    for d in deltas:
        tw = float(d.target_weight)
        if d.instrument_key in adj_w:
            tw = _clip_weight(float(d.target_weight), adj_w[d.instrument_key])
        px = float(prices.get(d.instrument_key) or 0.0)
        if px > 0 and eq > 0:
            tq = (tw * eq) / px
        else:
            tq = float(d.target_quantity)
            # 若有 quantity 调整意图但无价格，保持比例
            if d.instrument_key in adj_w and abs(float(d.target_weight)) > 1e-12:
                tq = float(d.target_quantity) * (
                    abs(tw) / abs(float(d.target_weight))
                )
        cq = float(d.current_quantity)
        cw = float(d.current_weight)
        dq = tq - cq
        dw = tw - cw
        if abs(dq) < 1e-12 and abs(dw) < 1e-12:
            side = "FLAT"
        elif dq > 0 or (abs(dq) < 1e-12 and dw > 0):
            side = "BUY"
        else:
            side = "SELL"
        out.append(
            PositionDelta(
                instrument_key=d.instrument_key,
                current_weight=cw,
                target_weight=tw,
                delta_weight=dw,
                current_quantity=cq,
                target_quantity=tq,
                delta_quantity=dq,
                side=side,  # type: ignore[arg-type]
                notional=abs(dq) * px,
            )
        )
    return out


def aggregate_decision(
    context: RiskContext, results: Sequence[RiskResult]
) -> RiskDecision:
    """聚合规则 → verdict + adjusted_deltas + violations。"""
    verdict = merge_verdicts(results)
    violations = [
        RiskViolation(
            rule_code=r.rule_code,
            instrument_key=r.instrument_key,
            message=r.message,
            severity=r.severity,
            original_value=r.original_value,
            limit_value=r.limit_value,
        )
        for r in results
        if r.decision in ("REJECT", "MODIFY", "ALLOW_REDUCE", "ERROR")
    ]

    if is_blocking(verdict):
        return RiskDecision(
            verdict=verdict,
            results=list(results),
            violations=violations,
            adjusted_deltas=[],
            message="; ".join(v.message for v in violations[:5]) or str(verdict),
        )

    adjusted = list(context.deltas)
    if verdict in ("MODIFY", "ALLOW_REDUCE"):
        adjusted = apply_modifications(
            context.deltas,
            results,
            equity=context.equity,
            prices=dict(context.prices),
        )
        # 二次保证：不抬高 |target_weight|
        safe: list[PositionDelta] = []
        orig = {d.instrument_key: d for d in context.deltas}
        for d in adjusted:
            o = orig.get(d.instrument_key)
            if o is None:
                continue
            tw = _clip_weight(float(o.target_weight), float(d.target_weight))
            if abs(tw - float(d.target_weight)) > 1e-12:
                px = float(context.prices.get(d.instrument_key) or 0.0)
                eq = max(float(context.equity), 0.0)
                tq = (tw * eq / px) if px > 0 and eq > 0 else float(d.target_quantity)
                dq = tq - float(d.current_quantity)
                side = (
                    "FLAT"
                    if abs(dq) < 1e-12
                    else ("BUY" if dq > 0 else "SELL")
                )
                d = d.model_copy(
                    update={
                        "target_weight": tw,
                        "target_quantity": tq,
                        "delta_quantity": dq,
                        "delta_weight": tw - float(d.current_weight),
                        "side": side,
                        "notional": abs(dq) * px,
                    }
                )
            safe.append(d)
        adjusted = safe

    return RiskDecision(
        verdict=verdict,
        results=list(results),
        violations=violations,
        adjusted_deltas=adjusted,
        message=str(verdict),
    )
