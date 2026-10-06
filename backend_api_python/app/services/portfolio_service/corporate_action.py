"""Corporate Action Contract + stub applier（对齐 Canonical schema）。"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

from .events import make_event
from .protocol import PositionEvent, PortfolioState

CorporateActionType = Literal["split", "bonus", "dividend", "rights", "merger"]


class CorporateAction(_ContractModel):
    """公司行为契约（与 corporate_action@1 字段对齐）。"""

    instrument_key: str
    effective_date: str
    action_type: CorporateActionType | str
    cash_dividend: float = 0.0
    split_ratio: float = 1.0
    rights_ratio: float = 0.0
    rights_price: float = 0.0
    currency: str = "CNY"
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def actions_to_events(
    state: PortfolioState,
    actions: Sequence[CorporateAction | Mapping[str, Any]],
) -> list[PositionEvent]:
    """将 CA 转为 PositionEvent；无持仓时 skip。"""
    out: list[PositionEvent] = []
    for raw in actions:
        if isinstance(raw, CorporateAction):
            ca = raw
        else:
            ca = CorporateAction.model_validate(dict(raw))
        pos = state.positions.get(ca.instrument_key)
        if pos is None or abs(float(pos.quantity)) < 1e-12:
            continue
        at = str(ca.action_type).lower()
        if at in ("split", "bonus"):
            ratio = float(ca.split_ratio) or 1.0
            if at == "bonus" and ratio == 1.0:
                # bonus 可能用 rights_ratio 表示送股比例
                ratio = 1.0 + float(ca.rights_ratio or 0.0)
            new_q = float(pos.quantity) * ratio
            out.append(
                make_event(
                    portfolio_id=state.portfolio.portfolio_id,
                    account_id=state.account.account_id,
                    event_type="CORPORATE_ACTION",
                    instrument_key=ca.instrument_key,
                    trading_date=ca.effective_date,
                    quantity=new_q - float(pos.quantity),
                    payload={
                        "action_type": at,
                        "split_ratio": ratio,
                        "replace_qty": new_q,
                    },
                    message=f"{at} x{ratio}",
                    salt=f"ca|{at}|{ca.effective_date}|{ca.instrument_key}",
                )
            )
        elif at == "dividend":
            cash = float(ca.cash_dividend) * float(pos.quantity)
            if abs(cash) < 1e-12:
                continue
            out.append(
                make_event(
                    portfolio_id=state.portfolio.portfolio_id,
                    account_id=state.account.account_id,
                    event_type="CORPORATE_ACTION",
                    instrument_key=ca.instrument_key,
                    trading_date=ca.effective_date,
                    cash_delta=cash,
                    payload={"action_type": "dividend", "cash_dividend": ca.cash_dividend},
                    message=f"dividend {cash}",
                    salt=f"ca|div|{ca.effective_date}|{ca.instrument_key}",
                )
            )
        elif at in ("rights", "merger"):
            # stub：记审计事件，具体数量留给后续
            out.append(
                make_event(
                    portfolio_id=state.portfolio.portfolio_id,
                    account_id=state.account.account_id,
                    event_type="CORPORATE_ACTION",
                    instrument_key=ca.instrument_key,
                    trading_date=ca.effective_date,
                    payload={"action_type": at, "stub": True, **ca.model_dump(mode="json")},
                    message=f"{at} stub",
                    salt=f"ca|{at}|{ca.effective_date}|{ca.instrument_key}",
                )
            )
    return out


class CorporateActionApplier:
    """stub：生成事件；由 reducer 真正改状态。"""

    def apply(
        self, state: PortfolioState, actions: Sequence[CorporateAction | Mapping[str, Any]]
    ) -> list[PositionEvent]:
        if not actions:
            return []
        return actions_to_events(state, actions)
