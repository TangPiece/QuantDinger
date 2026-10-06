#!/usr/bin/env python3
"""Phase 6B 验收：Portfolio & Position Service。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6b_portfolio_service.py
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
    pkg = ROOT / "app" / "services" / "portfolio_service"
    for py in pkg.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    if name == "qlib" or name.startswith("qlib."):
                        return False
                    if "broker" in name.lower() or "PendingOrder" in name:
                        return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("qlib") or "strategy_v2" in mod:
                    return False
                if "broker" in mod.lower() or "pending_order" in mod.lower():
                    return False
    return True


def main() -> int:
    from portfolio_service_golden.golden import (
        DAY,
        INST_A,
        make_env,
        prices,
        targets,
    )
    from app.services.portfolio_service.corporate_action import CorporateAction

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6b_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    acct = svc.open_account(environment="PAPER", initial_cash=1_000_000)
    checks["open_account"] = acct.status == "ACTIVE"
    pid = acct.metadata["default_portfolio_id"]
    svc.bind_runtime(acct.account_id, "rt_verify", bundle_hash="bh")

    r1 = svc.apply_targets(
        acct.account_id,
        targets(),
        runtime_id="rt_verify",
        run_id="run1",
        trading_date=DAY.isoformat(),
        prices=prices(),
    )
    checks["apply_ok"] = r1.status == "OK"
    checks["has_deltas"] = len(r1.deltas) > 0
    checks["has_fills"] = any(e.event_type == "BUY_FILLED" for e in r1.events)
    checks["snapshot"] = r1.snapshot is not None and r1.snapshot.equity > 0
    checks["exposure"] = r1.exposure.gross_exposure > 0

    positions = svc.get_positions(pid)
    checks["positions"] = any(p.instrument_key == INST_A for p in positions)
    checks["qty_invariant"] = all(
        abs(p.quantity - (p.available_quantity + p.frozen_quantity)) < 1e-6
        for p in positions
    )

    r2 = svc.apply_targets(
        acct.account_id,
        targets(),
        runtime_id="rt_verify",
        run_id="run1",
        trading_date=DAY.isoformat(),
        prices=prices(),
    )
    checks["idempotent"] = r2.status == "SKIPPED_IDEMPOTENT" and r2.reused

    # SHADOW dry
    sh = svc.open_account(environment="SHADOW", initial_cash=500_000)
    rd = svc.apply_targets(
        sh.account_id,
        targets(),
        trading_date=DAY.isoformat(),
        prices=prices(),
    )
    checks["shadow_dry"] = rd.apply_mode == "SHADOW_DRY" and not any(
        e.event_type == "BUY_FILLED" for e in rd.events
    )

    # CA stub
    rca = svc.apply_targets(
        acct.account_id,
        targets(w_a=0.2, w_b=0.1),
        runtime_id="rt_verify",
        run_id="run_ca",
        trading_date=DAY.isoformat(),
        prices=prices(),
        corporate_actions=[
            CorporateAction(
                instrument_key=INST_A,
                effective_date=DAY.isoformat(),
                action_type="split",
                split_ratio=2.0,
            )
        ],
    )
    checks["corporate_action"] = any(
        e.event_type == "CORPORATE_ACTION" for e in rca.events
    )

    recon = svc.reconcile(
        acct.account_id,
        external_cash={"available_cash": 0.0, "frozen_cash": 0.0},
    )
    checks["recon_contract"] = recon.status in (
        "MISMATCH",
        "RECONCILIATION_REQUIRED",
        "MATCHED",
    )

    checks["registry_account"] = bool(
        registry.get_production_account(acct.account_id)
    )
    checks["registry_apply"] = bool(
        registry.get_apply_by_idempotency(r1.idempotency_key)
    )

    print(json.dumps({"ok": all(checks.values()), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
