"""ExecutionCompatibility：声明 Qlib 对 5C 语义的支持级别。"""

from __future__ import annotations

from .protocol import CompatibilityItem, CompatibilityReport, QlibStrategySpec


def assess_compatibility(spec: QlibStrategySpec) -> CompatibilityReport:
    """按 realism 生成兼容性矩阵（禁止静默声称完全一致）。"""
    items: list[CompatibilityItem] = [
        CompatibilityItem(
            capability="weight_from_target_position",
            level="SUPPORTED",
            note="QuantDingerWeightStrategy from 5A TargetPosition",
        ),
        CompatibilityItem(
            capability="deal_price_open_close",
            level="SUPPORTED",
            note="NEXT_OPEN/NEXT_CLOSE via exchange_map.deal_price",
        ),
        CompatibilityItem(
            capability="native_qlib_topk_reselect",
            level="UNSUPPORTED",
            note="v1 does not re-select; preserves QD portfolio semantics",
        ),
        CompatibilityItem(
            capability="twap_vwap_level2",
            level="UNSUPPORTED",
            note="deferred",
        ),
    ]
    if spec.realism == "GROSS":
        items.append(
            CompatibilityItem(
                capability="commission_stamp_slippage_lot",
                level="SUPPORTED",
                note="GROSS: zero-cost path; QD NoCost equivalent",
            )
        )
        items.append(
            CompatibilityItem(
                capability="t_plus_order_intent",
                level="UNSUPPORTED",
                note="GROSS ignores T+1 sellable ledger",
            )
        )
        items.append(
            CompatibilityItem(
                capability="limit_up_down_suspend",
                level="UNSUPPORTED",
                note="GROSS ignores trading constraints",
            )
        )
    else:
        items.append(
            CompatibilityItem(
                capability="commission_stamp_slippage_lot",
                level="PARTIAL",
                note="Qlib bilateral open/close_cost ≠ 5C OrderIntent ledger",
            )
        )
        items.append(
            CompatibilityItem(
                capability="t_plus_order_intent",
                level="UNSUPPORTED",
                note="Qlib exchange lacks 5C T+1 sellable / OrderIntent path",
            )
        )
        items.append(
            CompatibilityItem(
                capability="limit_up_down_suspend",
                level="PARTIAL",
                note="limit_threshold approximate only",
            )
        )

    has_u = any(i.level == "UNSUPPORTED" for i in items)
    has_p = any(i.level == "PARTIAL" for i in items)
    return CompatibilityReport(
        realism=spec.realism,
        market_rule=spec.market_rule,
        items=items,
        has_unsupported=has_u,
        has_partial=has_p,
    )
