"""MiningPolicy preset 注册。"""

from __future__ import annotations

from .policy import MiningPolicy

_REGISTRY: dict[str, MiningPolicy] = {}


def register_policy(policy: MiningPolicy) -> None:
    _REGISTRY[policy.policy_id] = policy


def get_policy(policy_id: str) -> MiningPolicy:
    if policy_id not in _REGISTRY:
        raise KeyError(f"unknown mining policy: {policy_id}")
    return _REGISTRY[policy_id]


def _bootstrap() -> None:
    register_policy(
        MiningPolicy(
            policy_id="default_mining_small_v1",
            version="1.0.0",
            name="Small exhaustive grid",
            generator="exhaustive_small",
            max_candidates=32,
            max_depth=2,
            corr_dedup_enabled=False,
        )
    )
    register_policy(
        MiningPolicy(
            policy_id="default_mining_random_v1",
            version="1.0.0",
            name="Random search",
            generator="random_search",
            max_candidates=48,
            max_depth=2,
            corr_dedup_enabled=True,
            corr_dedup_top_n=10,
        )
    )
    register_policy(
        MiningPolicy(
            policy_id="phase9d_golden_v1",
            version="1.0.0",
            name="Golden CI mining",
            generator="exhaustive_small",
            max_candidates=16,
            max_depth=1,
            momentum_windows=[5, 10],
            volatility_windows=[10],
            rolling_windows=[5],
            ratio_pairs=[("close", "open")],
            fast_screen_min_ic=0.0,
            max_full_evaluations=8,
        )
    )


_bootstrap()

__all__ = ["get_policy", "register_policy"]
