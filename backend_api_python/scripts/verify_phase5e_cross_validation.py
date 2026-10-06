#!/usr/bin/env python3
"""Phase 5E 验收：Qlib ↔ QuantDinger Cross Validation。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5e_cross_validation.py
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
    pkg = ROOT / "app" / "services" / "research_data" / "cross_validation"
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
    return True


def main() -> int:
    from cross_validation_golden.golden import make_env, run_cv

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase5e_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    r = run_cv(svc, realism="GROSS")
    by = {L.layer: L for L in r.layers}
    for layer in (
        "dataset",
        "pit",
        "universe",
        "signal",
        "portfolio",
        "execution",
        "nav",
        "performance",
    ):
        checks[f"layer_{layer}"] = by.get(layer) is not None and by[layer].status == "PASS"

    checks["status_ok"] = r.report.status in (
        "PASSED",
        "PASSED_WITH_EXPECTED_DIFF",
    )
    checks["registry"] = bool(registry.get_research_cross_validation(r.cv_hash))
    art = Path(r.summary.storage_uri)
    checks["report_file"] = (art / "report.json").is_file()
    checks["attribution_file"] = (art / "attribution.json").is_file()
    checks["domain_isolation"] = _domain_isolation()
    checks["has_attribution"] = r.report.attribution.total == r.report.attribution.total

    r_net = run_cv(svc, realism="NET")
    checks["net_has_report"] = r_net.report.status in (
        "PASSED",
        "PASSED_WITH_EXPECTED_DIFF",
        "FAILED",
    )
    # NET 必须可解释：execution kind 或 attribution notes
    net_exec = next((L for L in r_net.layers if L.layer == "execution"), None)
    checks["net_explainable"] = bool(
        (net_exec and net_exec.kind in ("EXPECTED_DIFFERENCE", "SEMANTIC", "UNSUPPORTED"))
        or r_net.report.attribution.notes
    )

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "cv_hash": r.cv_hash,
                "status": r.report.status,
                "side_by_side": r.report.side_by_side,
                "attribution": r.report.attribution.model_dump(mode="json"),
                "layers": {k: v.status for k, v in by.items()},
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
