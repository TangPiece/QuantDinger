#!/usr/bin/env python3
"""验证 Qlib Cache 真读回：Calendar / Instruments / Features / DataHandler / DataQuery 一致性。

用法（在 backend_api_python 下）::

    QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \\
      python scripts/verify_qlib_cache_readback.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")


def main() -> int:
    try:
        import qlib  # noqa: F401
        from qlib.data import D
    except ImportError:
        print(json.dumps({"ok": False, "error": "pyqlib not installed"}, ensure_ascii=False))
        return 2

    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.ingest.build_golden import build_golden_dataset
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
    from app.services.research_data.qlib_materializer.validation import (
        compare_feature_values,
        validate_datahandler,
        validate_qlib_provider,
    )
    from app.services.research_data.registry import LocalJsonRegistry

    root = Path(tempfile.mkdtemp(prefix="qd_qlib_verify_"))
    store = LocalCanonicalStore(root=root / "canonical")
    registry = LocalJsonRegistry(root=root / "registry")
    golden = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        universe_version="verify.1",
        snapshot_id="snap_verify_qlib",
        use_fixture=True,
    )
    query = DataQuery(store, registry)
    mat = DefaultQlibMaterializer(query, cache_root=root / "cache")
    result = mat.materialize(golden["dataset_ref"], force=True)
    cache = Path(result.cache_path)
    handle = query.dataset(golden["dataset_ref"])

    report: dict = {
        "ok": True,
        "dataset_ref": golden["dataset_ref"],
        "dataset_hash": result.dataset_hash,
        "materialization_id": result.materialization_id,
        "cache_path": str(cache),
        "qlib_version": getattr(__import__("qlib"), "__version__", "unknown"),
        "checks": {},
    }

    # 1) Provider / D.features 非空
    provider = validate_qlib_provider(
        cache,
        expect_calendar_count=result.calendar_count,
        expect_instrument_count=result.instrument_count,
        sample_instrument="sz000001",
        sample_field="close",
    )
    report["checks"]["provider"] = provider
    if provider.get("via") != "qlib" or int(provider.get("sample_rows") or 0) <= 0:
        report["ok"] = False
        report["error"] = "provider readback failed"
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 1

    # 2) Calendar vs DataQuery
    members = query.universe(
        handle.definition.universe_code,
        date(2024, 3, 1),
        snapshot_id=handle.definition.snapshot_id,
        universe_version=handle.definition.universe_version,
    )
    dq_cal = query.trading_calendar(
        members,
        date(1970, 1, 1),
        date(2100, 1, 1),
        price_policy=handle.definition.price_policy,
    )
    qlib_cal = [
        d.date() if hasattr(d, "date") else d
        for d in D.calendar(
            start_time=dq_cal[0].isoformat(),
            end_time=dq_cal[-1].isoformat(),
            freq="day",
        )
    ]
    cal_ok = list(qlib_cal) == list(dq_cal)
    report["checks"]["calendar"] = {
        "ok": cal_ok,
        "dq_count": len(dq_cal),
        "qlib_count": len(qlib_cal),
        "min": str(dq_cal[0]),
        "max": str(dq_cal[-1]),
    }
    if not cal_ok:
        report["ok"] = False

    # 3) Instruments 小写
    listed = {
        str(x).lower()
        for x in D.list_instruments(
            D.instruments(market="all"),
            start_time=dq_cal[0].isoformat(),
            end_time=dq_cal[-1].isoformat(),
            as_list=True,
        )
    }
    expected = {to_qlib_instrument(ik).lower() for ik in members}
    inst_ok = listed == expected
    report["checks"]["instruments"] = {"ok": inst_ok, "qlib": sorted(listed), "expected": sorted(expected)}
    if not inst_ok:
        report["ok"] = False

    # 4) DataHandler
    try:
        handler = validate_datahandler(
            cache,
            instruments=sorted(expected),
            start=dq_cal[0].isoformat(),
            end=dq_cal[-1].isoformat(),
        )
        report["checks"]["datahandler"] = {"ok": True, **handler}
    except Exception as exc:
        report["checks"]["datahandler"] = {"ok": False, "error": str(exc)}
        report["ok"] = False

    # 5) feature mapping
    mapping = json.loads((cache / "metadata" / "feature_mapping.json").read_text(encoding="utf-8"))
    map_ok = mapping.get("close", {}).get("qlib_feature") == "$close"
    report["checks"]["feature_mapping"] = {"ok": map_ok, "close": mapping.get("close")}
    if not map_ok:
        report["ok"] = False

    # 6) DataQuery vs D.features
    market = query.market(
        members[:10],
        dq_cal[0],
        dq_cal[min(19, len(dq_cal) - 1)],
        price_policy=handle.definition.price_policy,
    )
    consistency_ok = True
    samples = 0
    for ik in members[:10]:
        qlib_id = to_qlib_instrument(ik).lower()
        part = market[market["instrument_key"] == ik].sort_values("trading_date")
        if part.empty:
            continue
        start = str(part.iloc[0]["trading_date"])
        end = str(part.iloc[-1]["trading_date"])
        feat = D.features([qlib_id], ["$close"], start_time=start, end_time=end)
        if feat.empty:
            consistency_ok = False
            break
        # MultiIndex (instrument, datetime) or datetime index
        series = feat.iloc[:, 0]
        dq_vals = [float(x) for x in part["close"].tolist()]
        q_vals = [float(x) for x in series.tolist()]
        # 对齐长度：按日期交集
        feat_dates = [
            (idx[1].date() if isinstance(idx, tuple) else idx.date())
            if hasattr(idx if not isinstance(idx, tuple) else idx[1], "date")
            else idx
            for idx in series.index
        ]
        # 简化：直接按行序（同日历对齐）
        n = min(len(dq_vals), len(q_vals))
        try:
            compare_feature_values(dq_vals[:n], q_vals[:n], atol=1e-8, rtol=1e-6)
            samples += n
        except Exception as exc:
            consistency_ok = False
            report["checks"]["consistency_error"] = str(exc)
            break
    report["checks"]["consistency"] = {"ok": consistency_ok, "compared_points": samples}
    if not consistency_ok:
        report["ok"] = False

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
