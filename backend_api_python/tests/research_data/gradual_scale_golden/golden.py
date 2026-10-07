"""Phase 7E Golden：Fake registry + TradingGovernanceService 脚手架。"""

from __future__ import annotations

import os
from pathlib import Path

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import ReadinessRunSummary
from app.services.research_data.registry import LocalJsonRegistry
from app.services.trading_governance.protocol import CapacityLimit, StrategyTarget
from app.services.trading_governance.runner import TradingGovernanceService

ACCOUNT_A = "gov-acct-a"
ACCOUNT_B = "gov-acct-b"
STRATEGY_A = "gov_strat_a"
STRATEGY_B = "gov_strat_b"
STRATEGY_C = "gov_strat_c"
VERSION_V1 = "sv_v1"
VERSION_V2 = "sv_v2"


def make_governance_env(tmp: Path) -> tuple[TradingGovernanceService, LocalJsonRegistry]:
    cache = tmp / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=cache / "registry")
    os.environ["PRODUCTION_READY"] = "true"
    os.environ.pop("LIVE_ENV_APPROVAL", None)

    registry.upsert_readiness_run(
        ReadinessRunSummary(
            run_id="gov_golden_rdy",
            production_ready=True,
            metadata={"source": "golden"},
        )
    )

    gov = TradingGovernanceService(store, registry)
    gov.register_account(ACCOUNT_A)
    gov.register_account(ACCOUNT_B)
    for sid, ver in (
        (STRATEGY_A, VERSION_V1),
        (STRATEGY_B, VERSION_V1),
        (STRATEGY_C, VERSION_V1),
    ):
        gov.register_strategy_version(
            strategy_id=sid,
            strategy_version=ver,
            model_version="mv1",
            dataset_hash="dh1",
            feature_version="fv1",
        )
        gov.bind_strategy_account(sid, ACCOUNT_A)
    gov.register_strategy_version(
        strategy_id=STRATEGY_A,
        strategy_version=VERSION_V2,
        model_version="mv2",
        dataset_hash="dh2",
        feature_version="fv2",
    )
    return gov, registry


def seed_l1_controlled(gov: TradingGovernanceService) -> None:
    gov.allocate_capital(
        account_id=ACCOUNT_A, strategy_id=STRATEGY_A, allocated_notional=5000.0
    )
    gov.set_capacity(
        CapacityLimit(strategy_id=STRATEGY_A, max_notional=3000.0, max_order_size=5.0)
    )
    gov.set_risk_budget(
        gov.default_risk_layers(
            account_id=ACCOUNT_A,
            strategy_id=STRATEGY_A,
            account_max=8000.0,
            strategy_max=2500.0,
        )
    )
    from app.services.trading_governance.protocol import ScaleState

    gov._scale[STRATEGY_A] = ScaleState(
        strategy_id=STRATEGY_A,
        account_id=ACCOUNT_A,
        current_level="L1_CONTROLLED",
    )
    lc = gov._lifecycle[STRATEGY_A]
    gov._lifecycle[STRATEGY_A] = lc.model_copy(update={"scale_level": "L1_CONTROLLED"})


def two_strategy_targets() -> tuple[StrategyTarget, StrategyTarget]:
    return (
        StrategyTarget(
            strategy_id=STRATEGY_A,
            instrument_key="USStock:AAPL",
            side="BUY",
            quantity=100.0,
        ),
        StrategyTarget(
            strategy_id=STRATEGY_B,
            instrument_key="USStock:AAPL",
            side="BUY",
            quantity=200.0,
        ),
    )
