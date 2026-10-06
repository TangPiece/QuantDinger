#!/usr/bin/env python3
"""Phase 6C 验收：Risk Engine。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6c_risk_engine.py
"""

from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def _domain_isolation() -> bool:
    pkg = ROOT / "app" / "services" / "risk_engine"
    for py in pkg.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    if name == "qlib" or name.startswith("qlib."):
                        return False
                    if "broker" in name.lower():
                        return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("qlib") or "strategy_v2" in mod or "live_trading" in mod:
                    return False
                if "broker" in mod.lower() or "pending_order" in mod.lower():
                    return False
    return True


def main() -> int:
    from risk_engine_golden.golden import (
        DAY,
        INST_A,
        default_policy,
        make_env,
        prices,
        sample_deltas,
        targets,
    )
    from app.services.portfolio_service.protocol import Account, CashBalance

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6c_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, portfolio, risk = make_env(tmp)
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    acct = Account(
        account_id="v_acc",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    pol = risk.register_policy(default_policy())
    checks["register_policy"] = bool(pol.policy_hash)

    r_mod = risk.evaluate(
        deltas=sample_deltas(tw_a=0.15),
        account=acct,
        policy=default_policy(clip_on_limit=True),
        prices=prices(),
        metadata={
            "account_id": "v_acc",
            "portfolio_id": "v_pf",
            "trading_date": DAY.isoformat(),
            "apply_id": "v_ap_mod",
        },
    )
    checks["modify_clip"] = (
        r_mod.verdict == "MODIFY"
        and len(r_mod.order_intents) > 0
        and abs(r_mod.adjusted_deltas[0].target_weight - 0.10) < 1e-9
    )

    r_rej = risk.evaluate(
        deltas=sample_deltas(tw_a=0.15),
        account=acct,
        policy=default_policy(clip_on_limit=False),
        prices=prices(),
        metadata={
            "account_id": "v_acc",
            "portfolio_id": "v_pf",
            "trading_date": DAY.isoformat(),
            "apply_id": "v_ap_rej",
        },
    )
    checks["reject"] = r_rej.verdict == "REJECT" and not r_rej.order_intents

    r_ok = risk.evaluate(
        deltas=sample_deltas(tw_a=0.05),
        account=acct,
        policy=default_policy(),
        prices=prices(),
        metadata={
            "account_id": "v_acc",
            "portfolio_id": "v_pf",
            "trading_date": DAY.isoformat(),
            "apply_id": "v_ap_ok",
        },
    )
    checks["allow_intents"] = r_ok.verdict == "ALLOW" and len(r_ok.order_intents) > 0
    checks["events"] = len(r_ok.events) >= 1
    checks["snapshot"] = r_ok.snapshot is not None

    r2 = risk.evaluate(
        deltas=sample_deltas(tw_a=0.05),
        account=acct,
        policy=default_policy(),
        prices=prices(),
        metadata={
            "account_id": "v_acc",
            "portfolio_id": "v_pf",
            "trading_date": DAY.isoformat(),
            "apply_id": "v_ap_ok",
        },
    )
    checks["idempotent"] = r2.status == "SKIPPED_IDEMPOTENT"

    # 6B SHADOW_DRY → 6C
    sh = portfolio.open_account(environment="SHADOW", initial_cash=1_000_000)
    apply = portfolio.apply_targets(
        sh.account_id,
        targets(w_a=0.08, w_b=0.05),
        trading_date=DAY.isoformat(),
        prices=prices(),
        apply_mode="SHADOW_DRY",
        runtime_id="rt_v",
        run_id="run_v",
    )
    rr = risk.evaluate(
        apply,
        policy=default_policy(max_single_position_weight=0.2),
        prices=prices(),
    )
    checks["shadow_pipeline"] = rr.verdict in (
        "ALLOW",
        "MODIFY",
        "ALLOW_REDUCE",
    ) and len(rr.order_intents) > 0

    checks["registry_run"] = bool(
        registry.get_risk_run_by_idempotency(r_ok.idempotency_key)
    )
    checks["no_broker_id"] = all(
        "broker" not in (i.reason or "").lower() for i in rr.order_intents
    )

    # clip-only sanity
    checks["clip_only"] = abs(r_mod.adjusted_deltas[0].target_weight) <= 0.15 + 1e-12

    print(json.dumps({"ok": all(checks.values()), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
