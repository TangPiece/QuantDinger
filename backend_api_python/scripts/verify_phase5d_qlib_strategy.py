#!/usr/bin/env python3
"""Phase 5D 验收：Qlib Strategy Adapter（无 pyqlib 时走合成路径）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase5d_qlib_strategy.py
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


def _domain_no_qlib_import() -> bool:
    """Domain 包（除 worker_main）不得 import qlib / Production。"""
    pkg = (
        ROOT
        / "app"
        / "services"
        / "research_data"
        / "qlib_strategy"
    )
    for py in pkg.glob("*.py"):
        if py.name == "worker_main.py":
            continue
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
    from app.services.research_data.qlib_materializer.instrument_mapper import (
        to_qlib_instrument,
    )
    from app.services.research_data.qlib_strategy import (
        assess_compatibility,
        compute_qlib_run_hash,
        targets_to_weight_series,
        to_prediction_series,
        weights_close_to,
    )
    from qlib_strategy_golden.golden import (
        INST_A,
        INST_B,
        default_spec,
        make_env,
        run_adapter,
        signal_rows,
        targets_by_date,
        trading_days,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase5d_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    # L1 instrument
    checks["instrument_map"] = (
        to_qlib_instrument(INST_A).lower() == "sh600000"
        and to_qlib_instrument(INST_B).lower() == "sz000001"
    )

    days = trading_days(4)
    # L2 signal
    pred = to_prediction_series(signal_rows(days[:3]))
    checks["signal_pred"] = not pred.empty and "sh600000" in {
        i for (_d, i) in pred.index
    }

    # L3 weights
    w = targets_to_weight_series(targets_by_date(days[:3]))
    checks["weights"] = weights_close_to(w, w) and not w.empty

    # Hash
    s_g = default_spec(days, realism="GROSS")
    s_n = default_spec(days, realism="NET")
    checks["hash_stable"] = compute_qlib_run_hash(s_g) == compute_qlib_run_hash(s_g)
    checks["hash_differs"] = compute_qlib_run_hash(s_g) != compute_qlib_run_hash(s_n)

    # Compatibility
    g_rep = assess_compatibility(s_g)
    n_rep = assess_compatibility(s_n)
    checks["gross_no_partial"] = not g_rep.has_partial
    checks["net_partial_unsupported"] = n_rep.has_partial and n_rep.has_unsupported

    # End-to-end synthetic (无 pyqlib)
    r_gross = run_adapter(svc, realism="GROSS", days=days)
    r_net = run_adapter(svc, realism="NET", days=days)
    art = Path(r_gross.summary.storage_uri)
    checks["gross_metrics"] = r_gross.summary.metrics_json.get("total_return") is not None
    checks["manifest"] = (art / "manifest.json").is_file()
    checks["compatibility_file"] = (art / "compatibility.json").is_file()
    checks["registry"] = bool(registry.get_research_qlib_run(r_gross.qlib_run_hash))
    checks["net_compat"] = bool(
        r_net.summary.compatibility_json.get("has_unsupported")
    )
    checks["domain_isolation"] = _domain_no_qlib_import()

    # pyqlib 可选：存在时仅标记，不强制跑实盘 backtest
    try:
        import qlib  # noqa: F401

        pyqlib_available = True
    except Exception:
        pyqlib_available = False

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "pyqlib_available": pyqlib_available,
                "qlib_run_hash": r_gross.qlib_run_hash,
                "gross_total_return": r_gross.summary.metrics_json.get("total_return"),
                "worker_mode": r_gross.worker_mode,
                "note": (
                    "synthetic path used when force_synthetic / no cache; "
                    "full qlib.init backtest skipped without pyqlib"
                ),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
