#!/usr/bin/env python3
"""Phase 4A 验收：Factor Lab Foundation。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4a_factor_lab.py
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

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.research_data.contracts import FeatureDefinition, PricePolicy
    from app.services.research_data.factor_lab import (
        FACTOR_LAB_CONTRACT_VERSION,
        FactorDatasetArtifactStore,
        build_factor_dataset_record,
        build_manifest,
        compute_factor_hash,
        register_factor,
        register_factor_dataset,
        validate_for_backtest,
    )
    from app.services.research_data.registry import (
        FeatureImmutabilityError,
        LocalJsonRegistry,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4a_"))
    reg = LocalJsonRegistry(root=tmp / "registry")

    feat = FeatureDefinition(
        code="momentum_20d",
        version="1.0.0",
        name="Momentum 20D",
        expression="close / Ref(close, 20) - 1",
        factor_type="TECHNICAL",
        computation_engine="quantdinger",
        engine_version="1",
        dependencies=["market:CNStock"],
        information_policy="NON_PIT",
        price_policy=PricePolicy(adjustment="post"),
    )
    registered = register_factor(reg, feat)
    h1 = compute_factor_hash(registered)
    h2 = compute_factor_hash(registered)
    hash_ok = h1 == h2 == registered.factor_hash

    imm_ok = False
    try:
        register_factor(
            reg,
            feat.model_copy(update={"expression": "close / Ref(close, 10) - 1"}),
        )
    except FeatureImmutabilityError:
        imm_ok = True

    pit_ok = validate_for_backtest(
        FeatureDefinition(
            code="roe",
            version="1.0.0",
            name="ROE",
            expression="net_income / equity",
            factor_type="FUNDAMENTAL",
            information_policy="PIT_SAFE",
            dependencies=["fundamental:roe"],
        )
    ) and not validate_for_backtest(
        FeatureDefinition(
            code="unk",
            version="1.0.0",
            name="unk",
            expression="x",
            information_policy="UNKNOWN",
        )
    )

    rec = build_factor_dataset_record(
        registered,
        dataset_hash="ds_verify",
        snapshot_id="snap_verify",
        start_date="2024-01-01",
        end_date="2024-12-31",
        universe_code="CSI300",
    )
    register_factor_dataset(reg, rec)
    man = build_manifest(registered, rec, checksum="deadbeef", row_count=100)
    art = FactorDatasetArtifactStore(root=tmp / "art").write_manifest(man, record=rec)
    ds_ok = reg.get_factor_dataset(rec.factor_dataset_id).factor_dataset_id == rec.factor_dataset_id

    checks = {
        "factor_hash_determinism": hash_ok,
        "immutability": imm_ok,
        "pit_gate": pit_ok,
        "factor_dataset": ds_ok,
        "manifest_artifact": art.artifact_type == "factor_dataset",
        "contract_version": FACTOR_LAB_CONTRACT_VERSION == "qd_factor_lab@1",
    }
    all_ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": all_ok,
                "checks": checks,
                "factor_hash": registered.factor_hash,
                "factor_dataset_id": rec.factor_dataset_id,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
