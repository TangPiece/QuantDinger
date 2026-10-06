#!/usr/bin/env python3
"""Phase 6A 验收：Production Runtime / Online Data。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase6a_production_runtime.py
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
    pkg = ROOT / "app" / "services" / "production_runtime"
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
                if mod.startswith("qlib"):
                    return False
                if "broker" in mod.lower() or "pending_order" in mod.lower():
                    return False
                if "DataSourceFactory" in {
                    a.name for a in (node.names or [])
                }:
                    return False
    return True


def main() -> int:
    from production_runtime_golden.golden import (
        deployed_bundle,
        intraday_now,
        make_env,
        tick_meta,
        trading_days,
    )
    from app.services.production_runtime.session import MarketSchedule

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6a_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, bridge, rt = make_env(tmp)
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    sched = MarketSchedule()
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    sh = ZoneInfo("Asia/Shanghai")
    t = datetime(2020, 1, 2, 10, 30, tzinfo=sh).astimezone(timezone.utc)
    checks["session_intraday"] = sched.phase_at("CN_A", t) == "INTRADAY"

    dep = deployed_bundle(bridge)
    inst = rt.start(dep.bundle_hash, market="CN_A", environment="PAPER")
    checks["start_ready"] = inst.status == "READY"
    checks["manifest"] = Path(inst.storage_uri, "manifest.json").is_file()

    day = trading_days(1)[0]
    r1 = rt.tick(inst.runtime_id, now=intraday_now(day), metadata=tick_meta(day))
    checks["tick_ok"] = r1.status == "OK"
    checks["has_intents"] = len(r1.order_intents) > 0
    checks["events"] = "ORDER_INTENT_CREATED" in r1.events

    r2 = rt.tick(inst.runtime_id, now=intraday_now(day), metadata=tick_meta(day))
    checks["idempotent"] = r2.status == "SKIPPED_IDEMPOTENT" and r2.reused

    # DATA_STALE
    stale = rt.tick(
        inst.runtime_id,
        now=intraday_now(day),
        metadata={
            "trading_date": day.isoformat(),
            "session_phase": "INTRADAY",
            "decision_bucket": "STALE_VERIFY",
            "force_intraday": True,
            "instruments": ["CNStock:999999"],
        },
    )
    checks["data_stale"] = stale.status == "FAILED" and "DATA_STALE" in stale.events

    paused = rt.pause(inst.runtime_id)
    checks["pause"] = paused.status == "PAUSED"
    stopped = rt.stop(inst.runtime_id)
    checks["stop"] = stopped.status == "STOPPED"

    checks["registry_runtime"] = bool(
        registry.get_production_runtime(inst.runtime_id)
    )
    checks["event_log"] = len(registry.list_runtime_events(inst.runtime_id)) >= 2

    print(json.dumps({"ok": all(checks.values()), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
