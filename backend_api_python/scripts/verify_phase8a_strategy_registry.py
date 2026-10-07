#!/usr/bin/env python3
"""Phase 8A 验收：Strategy Registry（Fake bundle / LocalJson 默认）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8a_strategy_registry.py
"""

from __future__ import annotations

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


def main() -> int:
    from app.services.strategy_registry.protocol import ENGINE_VERSION
    from strategy_registry_golden.golden import (
        BUNDLE_HASH,
        STRATEGY_CODE,
        STRATEGY_VERSION,
        make_registry_env,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8a_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_strategy_registry@1"

    svc, registry, _ = make_registry_env(tmp)
    ver = svc.register_version_from_bundle(
        BUNDLE_HASH,
        strategy_version_label=STRATEGY_VERSION,
        risk_policy_ref="risk_default@v1",
    )
    checks["bundle_fields"] = bool(
        ver.dataset_hash and ver.model_version and ver.bundle_hash == BUNDLE_HASH
    )

    ver2 = svc.register_version_from_bundle(
        BUNDLE_HASH,
        strategy_version_label=STRATEGY_VERSION,
        risk_policy_ref="risk_default@v1",
    )
    checks["idempotent"] = ver.version_id == ver2.version_id

    immut = False
    try:
        svc.register_version_manual(
            STRATEGY_CODE,
            STRATEGY_VERSION,
            dataset_hash="mutated",
            bundle_hash=BUNDLE_HASH,
        )
    except Exception:
        immut = True
    checks["immutable_reject"] = immut

    r1 = svc.resolve(code=STRATEGY_CODE, version=STRATEGY_VERSION)
    r2 = svc.resolve(bundle_hash=BUNDLE_HASH)
    checks["resolve_consistent"] = r1.version_id == r2.version_id

    svc.link_governance_active(STRATEGY_CODE, STRATEGY_VERSION)
    lc = registry._read()["gov_strategy_lifecycle"][STRATEGY_CODE]
    checks["governance_active"] = lc.get("active_version") == STRATEGY_VERSION

    ok = all(checks.values())
    print(json.dumps({"phase": "8a", "ok": ok, "checks": checks}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
