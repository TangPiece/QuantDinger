#!/usr/bin/env python3
"""Phase 4H 验收：Factor Combination。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4h_factor_combination.py
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
    from app.services.research_data.factor_lab.combination import (
        compute_combination_hash,
    )
    from factor_lab_combination.golden import (
        FID_A,
        FID_B,
        default_spec,
        identical_panels,
        make_env,
        noisy_second_panels,
        orthogonal_panels,
        run_with_panels,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4h_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, svc = make_env(tmp)
    checks: dict[str, bool] = {}

    # 相同因子 → corr / 冗余
    a_id, b_id = identical_panels(40)
    r_id = run_with_panels(
        svc,
        a_id,
        b_id,
        default_spec(
            weight_method="CORR_ADJUSTED",
            member_ic={FID_A: 0.06, FID_B: 0.06},
            normalize="ZSCORE",
        ),
    )
    mat = r_id.frames.metadata["corr_summary"]["matrix"]
    checks["identical_corr"] = abs(mat[FID_A][FID_B] - 1.0) < 1e-9
    checks["redundancy"] = any(
        {p.factor_i, p.factor_j} == {FID_A, FID_B}
        for p in r_id.frames.redundancy_pairs
    )

    # IC_WEIGHT
    a_o, b_o = orthogonal_panels(40)
    r_ic = run_with_panels(
        svc,
        a_o,
        b_o,
        default_spec(
            weight_method="IC_WEIGHT",
            member_ic={FID_A: 0.06, FID_B: 0.03},
        ),
    )
    wmap = {w.factor_dataset_id: w.weight for w in r_ic.frames.weights}
    checks["ic_weight"] = (
        abs(wmap[FID_A] - 2.0 / 3.0) < 1e-9
        and abs(wmap[FID_B] - 1.0 / 3.0) < 1e-9
    )

    # EQUAL ZSCORE composite
    r_eq = run_with_panels(
        svc,
        a_o,
        b_o,
        default_spec(normalize="ZSCORE", weight_method="EQUAL"),
    )
    from app.services.research_data.factor_lab.combination.align import (
        CrossSectionAligner,
    )
    from app.services.research_data.factor_lab.combination.normalize import CSNormalizer

    spec_z = default_spec(normalize="ZSCORE", weight_method="EQUAL")
    aligned = CrossSectionAligner().align({FID_A: a_o, FID_B: b_o}, spec_z)
    norm = CSNormalizer().normalize(aligned, spec_z)
    checks["equal_composite"] = all(
        abs(c.composite - 0.5 * (n.values[FID_A] + n.values[FID_B])) < 1e-9
        for n, c in zip(norm, r_eq.frames.composite_rows)
    )

    # ORTHOGONALIZE
    a_n, b_n = noisy_second_panels(40, noise=0.05)
    r_ortho = run_with_panels(
        svc,
        a_n,
        b_n,
        default_spec(normalize="ZSCORE", weight_method="ORTHOGONALIZE"),
    )
    xs = [row.member_values[FID_A] for row in r_ortho.frames.composite_rows]
    ys = [row.member_values[FID_B] for row in r_ortho.frames.composite_rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    corr = num / (dx * dy) if dx and dy else 0.0
    checks["ortho_corr"] = abs(corr) < 1e-6

    # hash / manifest / registry
    spec = default_spec()
    h1 = compute_combination_hash(
        spec, member_hashes={FID_A: f"dh_{FID_A}", FID_B: f"dh_{FID_B}"}
    )
    h2 = compute_combination_hash(
        spec, member_hashes={FID_A: f"dh_{FID_A}", FID_B: f"dh_{FID_B}"}
    )
    r_hash = run_with_panels(svc, a_o, b_o, spec)
    checks["hash_repro"] = h1 == h2 == r_hash.combination_hash
    art = Path(r_hash.summary.storage_uri)
    checks["manifest"] = (art / "manifest.json").is_file()
    checks["registry"] = bool(
        registry.get_factor_combination(r_hash.combination_hash)
    )
    comp = registry.get_factor_dataset(r_hash.composite_factor_dataset_id)
    checks["factor_dataset_4c"] = comp.factor_ref.startswith("composite@c_")
    checks["raw_immutable"] = (
        registry.get_factor_dataset(FID_A).factor_ref == "raw_a@1.0.0"
        and registry.get_factor_dataset(FID_B).factor_ref == "raw_b@1.0.0"
    )

    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": checks,
                "combination_hash": r_hash.combination_hash,
                "ortho_corr": corr,
                "composite_factor_dataset_id": r_hash.composite_factor_dataset_id,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
