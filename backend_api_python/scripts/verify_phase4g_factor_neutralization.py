#!/usr/bin/env python3
"""Phase 4G 验收：Factor Neutralization。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4g_factor_neutralization.py
"""

from __future__ import annotations

import json
import math
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
    from app.services.research_data.factor_lab.neutralization import (
        compute_neutralization_hash,
    )
    from factor_lab_neutralization.golden import (
        FID,
        default_spec,
        make_env,
        size_industry_panel,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4g_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    factors, exposures, alphas = size_industry_panel(40)
    ex_size = [e for e in exposures if e["exposure_code"] == "SIZE"]
    spec = default_spec(targets=["SIZE"])

    r = svc.run(
        FID,
        spec,
        metadata={
            "factor_records": factors,
            "exposure_rows": ex_size,
            "force_recompute": True,
        },
    )
    neu = {
        x.instrument_key: x.neutralized_factor
        for x in r.frames.factor_rows
        if x.neutralized_factor is not None
    }
    a = alphas
    n = [neu[f"CNStock:{i:03d}"] for i in range(40)]
    ma, mn = sum(a) / len(a), sum(n) / len(n)
    num = sum((x - ma) * (y - mn) for x, y in zip(a, n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    dn = math.sqrt(sum((y - mn) ** 2 for y in n))
    corr = num / (da * dn) if da and dn else 0.0
    checks["alpha_recovery"] = corr > 0.95

    size_diag = next(
        d
        for d in r.frames.diagnostics
        if d.exposure_code == "SIZE" and d.status == "OK"
    )
    checks["corr_reduction"] = abs(size_diag.correlation_after or 0) < 0.05 and (
        (size_diag.correlation_before or 0) > 0.5
    )
    checks["r_squared"] = (size_diag.r_squared or 0) > 0.9

    r_si = svc.run(
        FID,
        default_spec(targets=["SIZE", "INDUSTRY"]),
        metadata={
            "factor_records": factors,
            "exposure_rows": exposures,
            "force_recompute": True,
        },
    )
    checks["size_industry"] = any(
        d.exposure_code == "INDUSTRY" for d in r_si.frames.diagnostics
    )

    h1 = compute_neutralization_hash(spec, factor_dataset_hash="dh_4g")
    h2 = compute_neutralization_hash(spec, factor_dataset_hash="dh_4g")
    checks["hash_repro"] = h1 == h2 == r.neutralization_hash

    art = Path(r.summary.storage_uri)
    checks["manifest"] = (art / "manifest.json").is_file()
    checks["registry"] = bool(registry.get_factor_neutralization(r.neutralization_hash))
    neut = registry.get_factor_dataset(r.neutralized_factor_dataset_id)
    checks["factor_dataset_4c"] = neut.factor_ref.startswith("neut_factor@")
    checks["raw_immutable"] = (
        registry.get_factor_dataset(FID).factor_ref == "raw_alpha@1.0.0"
    )

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "neutralization_hash": r.neutralization_hash,
                "alpha_corr": corr,
                "size_corr_before": size_diag.correlation_before,
                "size_corr_after": size_diag.correlation_after,
                "r_squared": size_diag.r_squared,
                "neutralized_factor_dataset_id": r.neutralized_factor_dataset_id,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
