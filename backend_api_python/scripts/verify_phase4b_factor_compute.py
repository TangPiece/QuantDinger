#!/usr/bin/env python3
"""Phase 4B 验收：Factor Computation Engine。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase4b_factor_compute.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Golden fixture 位于 tests/research_data/factor_lab_compute
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.research_data.contracts import FeatureDefinition, PricePolicy
    from app.services.research_data.factor_lab import (
        FactorComputeService,
        PITComputeContext,
        build_compute_plan,
        compute_result_dataset_hash,
        register_factor,
        resolve_dependency_dag,
        select_engine,
    )
    from app.services.research_data.factor_lab.compute.engines.duckdb_engine import (
        DuckDBFactorEngine,
    )
    from app.services.research_data.factor_lab.compute.engines.polars_engine import (
        PolarsFactorEngine,
    )
    from app.services.research_data.factor_lab.dependencies import FactorDependencyError
    from app.services.research_data.registry import LocalJsonRegistry
    from factor_lab_compute.golden import (
        INSTRUMENTS,
        make_env,
        register_momentum,
        register_roe,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase4b_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    _, registry, query, svc, days = make_env(tmp)

    def _ctx(**kw) -> PITComputeContext:
        base = dict(
            knowledge_time=datetime(2024, 5, 31, 15, 0, 0, tzinfo=timezone.utc),
            snapshot_id="snap_4b_verify",
            start_date=days[0].isoformat(),
            end_date=days[-1].isoformat(),
            exchange="CN",
            universe_code="",
            price_policy=PricePolicy(adjustment="none"),
            canonical_dataset_hash="input_ds_4b_verify",
        )
        base.update(kw)
        return PITComputeContext(**base)

    checks: dict[str, bool] = {}
    meta = {"instruments": INSTRUMENTS, "exchange": "CN"}

    # 1) DAG / cycle / missing dependency
    feat = register_momentum(registry)
    dag = resolve_dependency_dag(feat, registry)
    dag_ok = "market:CNStock" in dag.order and dag.root_ref == "momentum_20d@1.0.0"
    cycle_ok = False
    try:
        register_factor(
            registry,
            FeatureDefinition(
                code="cyc",
                version="1.0.0",
                name="cyc",
                expression="x",
                dependencies=["factor:cyc@1.0.0"],
            ),
        )
    except FactorDependencyError:
        cycle_ok = True
    missing_ok = False
    try:
        register_factor(
            LocalJsonRegistry(root=tmp / "r_miss"),
            FeatureDefinition(
                code="x",
                version="1.0.0",
                name="x",
                expression="momentum_20",
                dependencies=["factor:missing@1.0.0"],
            ),
        )
    except FactorDependencyError:
        missing_ok = True
    checks["dag_cycle_missing"] = dag_ok and cycle_ok and missing_ok

    # 2) ComputePlan 确定性
    ctx = _ctx()
    p1 = build_compute_plan(feat, ctx, registry)
    p2 = build_compute_plan(feat, ctx, registry)
    checks["plan_determinism"] = (
        p1.plan_hash == p2.plan_hash and select_engine(feat) == "quantdinger"
    )

    # 3–4) hash + 重复计算 reproducibility
    a = svc.run("momentum_20d@1.0.0", ctx, metadata=meta)
    b = svc.run("momentum_20d@1.0.0", ctx, metadata=meta)
    checks["result_hash_repro"] = (
        a.record.factor_dataset_id == b.record.factor_dataset_id
        and a.record.dataset_hash == b.record.dataset_hash
        and compute_result_dataset_hash(a.plan) == a.record.dataset_hash
        and a.frame.row_count == b.frame.row_count
        and a.frame.row_count > 0
    )

    # 5) 版本隔离
    register_factor(
        registry,
        FeatureDefinition(
            code="momentum_20d",
            version="1.1.0",
            name="Momentum 20D v1.1",
            expression="momentum_10",
            factor_type="TECHNICAL",
            computation_engine="quantdinger",
            dependencies=["market:CNStock"],
            information_policy="NON_PIT",
            price_policy=PricePolicy(adjustment="none"),
        ),
    )
    r0 = svc.run("momentum_20d@1.0.0", ctx, metadata=meta)
    r1 = svc.run("momentum_20d@1.1.0", ctx, metadata=meta)
    checks["version_isolation"] = (
        r0.record.factor_dataset_id != r1.record.factor_dataset_id
        and r0.record.factor_hash != r1.record.factor_hash
    )

    # 6) PIT leakage
    register_roe(registry)
    early = svc.run(
        "roe@1.0.0",
        _ctx(knowledge_time=datetime(2024, 5, 1, 12, 0, 0, tzinfo=timezone.utc)),
        metadata=meta,
    )
    late = svc.run(
        "roe@1.0.0",
        _ctx(knowledge_time=datetime(2024, 5, 10, 15, 0, 0, tzinfo=timezone.utc)),
        metadata=meta,
    )
    checks["pit_leakage"] = early.frame.row_count == 0 and late.frame.row_count > 0

    # 7) schema + manifest
    man_path = Path(a.record.storage_uri or "") / "manifest.json"
    got = registry.get_factor_dataset(a.record.factor_dataset_id)
    checks["schema_manifest"] = bool(
        a.record.checksum and a.record.storage_uri and man_path.is_file() and got.factor_ref
    )

    # 8) Polars vs DuckDB 数值容差
    registry.upsert_feature(
        FeatureDefinition(
            code="momentum_20d",
            version="duck1",
            name="m",
            expression="momentum_20",
            computation_engine="duckdb",
            dependencies=["market:CNStock"],
            information_policy="NON_PIT",
            price_policy=PricePolicy(adjustment="none"),
        )
    )
    plan_p = build_compute_plan(feat, ctx, registry).model_copy(
        update={"metadata": meta, "engine": "quantdinger"}
    )
    plan_d = build_compute_plan(
        registry.get_feature("momentum_20d@duck1"), ctx, registry
    ).model_copy(update={"metadata": meta})
    fp = PolarsFactorEngine().compute(plan_p, query=query, registry=registry)
    fd = DuckDBFactorEngine().compute(plan_d, query=query, registry=registry)
    mp = {(r["instrument_key"], r["trading_date"]): r["value"] for r in fp.records}
    md = {(r["instrument_key"], r["trading_date"]): r["value"] for r in fd.records}
    common = set(mp) & set(md)
    max_diff = max(abs(mp[k] - md[k]) for k in common) if common else 1.0
    checks["polars_vs_duckdb"] = bool(common) and max_diff < 1e-6

    # 9) Level2 adapter 列映射
    import pandas as pd

    register_factor(
        registry,
        FeatureDefinition(
            code="l2_imb",
            version="1.0.0",
            name="L2 imb",
            expression="l2_imbalance",
            computation_engine="level2",
            dependencies=["level2:imbalance"],
            information_policy="NON_PIT",
        ),
    )
    panel = pd.DataFrame(
        {
            "instrument_key": ["CNStock:600519", "CNStock:600519"],
            "trading_date": [days[0], days[1]],
            "l2_imbalance": [0.1, 0.2],
        }
    )
    l2 = svc.run(
        "l2_imb@1.0.0",
        ctx,
        metadata={"l2_panel": panel, "instruments": INSTRUMENTS},
    )
    checks["level2_adapter"] = (
        l2.frame.row_count == 2 and abs(l2.frame.records[0]["value"] - 0.1) < 1e-9
    )

    all_ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": all_ok,
                "checks": checks,
                "plan_hash": p1.plan_hash,
                "result_dataset_hash": a.record.dataset_hash,
                "factor_dataset_id": a.record.factor_dataset_id,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
