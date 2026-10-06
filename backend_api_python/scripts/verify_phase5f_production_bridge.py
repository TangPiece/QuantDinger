#!/usr/bin/env python3
"""Phase 5F 验收：Research → Production Bridge。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5f_production_bridge.py
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
    pkg = ROOT / "app" / "services" / "research_data" / "production_bridge"
    for py in pkg.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    if name == "qlib" or name.startswith("qlib."):
                        return False
                    if "backtest_production" in name:
                        return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("qlib") or "backtest_production" in mod:
                    return False
                for alias in node.names or []:
                    if alias.name == "ProductionBacktestEngine":
                        return False
    return True


def main() -> int:
    from production_bridge_golden.golden import (
        SCODE,
        make_env,
        promote_to_deployed,
        run_infer,
        trading_days,
        freeze_meta,
        SHASH,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase5f_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    r = promote_to_deployed(svc)
    checks["deployed"] = r.summary.status == "DEPLOYED"
    checks["manifest"] = (Path(r.summary.storage_uri) / "manifest.json").is_file()
    checks["checksums"] = (Path(r.summary.storage_uri) / "checksums.json").is_file()
    checks["registry"] = bool(registry.get_production_bundle(r.bundle_hash))
    checks["active"] = (
        registry.get_active_deployment(SCODE).bundle_hash == r.bundle_hash
    )

    day = trading_days(1)[0]
    resp = run_infer(svc, r.bundle_hash, day)
    checks["infer_ok"] = resp.status == "OK"
    checks["has_intents"] = len(resp.order_intents) > 0
    checks["dry_run"] = all(
        (i.reason or "").startswith("DRY_RUN") for i in resp.order_intents
    )

    # v2 + rollback
    meta = freeze_meta()
    meta["dataset_hash"] = "dh_5f_v2"
    meta["parent_bundle_hash"] = r.bundle_hash
    r2 = svc.freeze(SHASH, metadata=meta)
    r2 = svc.validate(r2.bundle_hash, metadata=meta)
    r2 = svc.promote(r2.bundle_hash)
    r2 = svc.approve(r2.bundle_hash)
    r2 = svc.deploy(r2.bundle_hash)
    rb = svc.rollback(SCODE, r.bundle_hash)
    checks["rollback"] = (
        rb.summary.bundle_hash == r.bundle_hash and rb.summary.status == "DEPLOYED"
    )
    checks["domain_isolation"] = _domain_isolation()

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "bundle_hash": r.bundle_hash,
                "infer_status": resp.status,
                "n_intents": len(resp.order_intents),
                "active_after_rollback": registry.get_active_deployment(
                    SCODE
                ).bundle_hash,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
