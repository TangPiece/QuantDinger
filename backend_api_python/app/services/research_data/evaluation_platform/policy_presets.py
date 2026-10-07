"""内置 EvaluationPolicy preset。"""

from __future__ import annotations

from app.services.research_data.factor_lab.evaluation.protocol import ReturnSpec
from app.services.research_data.factor_lab.groups.protocol import CostModelSpec

from .policy import EvaluationPolicy

DEFAULT_EQUITY_FACTOR_V1 = "default_equity_factor_v1"


def default_equity_factor_v1() -> EvaluationPolicy:
    """A 股因子默认：next_open_to_close、10 分位、EQUAL_WEIGHT 成本模型。"""
    return EvaluationPolicy(
        policy_id=DEFAULT_EQUITY_FACTOR_V1,
        version="1.0.0",
        name="Default equity factor evaluation v1",
        return_spec=ReturnSpec(
            definition="next_open_to_close",
            horizons=[1, 5],
            execution_delay=1,
        ),
        ic_direction="AUTO",
        min_cross_section_size=30,
        quantile_count=10,
        cost_model=CostModelSpec(kind="FIXED_BPS", buy_cost_bps=5.0, sell_cost_bps=10.0),
        annualization_trading_days=252,
    )


_PRESETS: dict[str, EvaluationPolicy] = {
    DEFAULT_EQUITY_FACTOR_V1: default_equity_factor_v1(),
}


def get_policy(policy_id: str) -> EvaluationPolicy:
    pid = str(policy_id or "").strip()
    if pid not in _PRESETS:
        raise KeyError(f"unknown evaluation policy: {policy_id!r}")
    return _PRESETS[pid].model_copy(deep=True)


def register_policy(policy: EvaluationPolicy) -> None:
    _PRESETS[policy.policy_id] = policy.model_copy(deep=True)


__all__ = [
    "DEFAULT_EQUITY_FACTOR_V1",
    "default_equity_factor_v1",
    "get_policy",
    "register_policy",
]
