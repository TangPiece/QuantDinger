#!/usr/bin/env python3
"""Phase 1D 一致性验收：Canonical → DataQuery → Materializer → pyqlib 闭环。

六项检查：
  1. pyqlib D.features 真读回
  2. DataQuery vs Qlib 全字段 OHLCV 面板
  3. PIT 门禁（DataQuery + Materializer 不调 fundamental）
  4. Universe 历史 as_of / 幸存者偏差
  5. price_policy none/post 经 Qlib；Canonical 不变
  6. dataset_hash rematerialize 可复现

用法（在 backend_api_python 下）::

    QUANTDINGER_SKIP_APP_INIT=1 MLFLOW_DISABLE_AGENT_HINT=1 \\
      python scripts/verify_phase1d_consistency.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
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
    from app.services.research_data.contracts import DatasetDefinition, PricePolicy
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.ingest.build_golden import (
        GOLDEN_DATASET_CODE,
        build_golden_dataset,
    )
    from app.services.research_data.phase1d_panel import build_pit_safe_research_panel
    from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
    from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
    from app.services.research_data.qlib_materializer.validation import (
        OHLCV_FIELDS,
        assert_canonical_raw_unchanged,
        compare_ohlcv_panels,
        compare_universe_sets,
        directory_sha256,
        qlib_features_to_frame,
        validate_qlib_provider,
    )
    from app.services.research_data.registry import LocalJsonRegistry

    root = Path(tempfile.mkdtemp(prefix="qd_phase1d_"))
    store = LocalCanonicalStore(root=root / "canonical")
    registry = LocalJsonRegistry(root=root / "registry")
    start, end = date(2024, 1, 1), date(2024, 6, 30)
    golden = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002", "CNStock:600000"],
        start=start,
        end=end,
        universe_version="phase1d.1",
        snapshot_id="snap_phase1d",
        use_fixture=True,
    )
    query = DataQuery(store, registry)
    mat = DefaultQlibMaterializer(query, cache_root=root / "cache", start=start, end=end)
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

    def fail(name: str, detail: dict) -> None:
        report["ok"] = False
        report["checks"][name] = {"ok": False, **detail}

    # --- 1) pyqlib 真读回 ---
    provider = validate_qlib_provider(
        cache,
        expect_calendar_count=result.calendar_count,
        expect_instrument_count=result.instrument_count,
        sample_instrument="sz000001",
        sample_field="close",
    )
    if provider.get("via") != "qlib" or int(provider.get("sample_rows") or 0) <= 0:
        fail("pyqlib_read", {"provider": provider, "error": "D.features required"})
    else:
        report["checks"]["pyqlib_read"] = {"ok": True, **provider}

    # --- 2) OHLCV 全字段面板 ---
    try:
        members = query.universe(
            handle.definition.universe_code,
            end,
            snapshot_id=handle.definition.snapshot_id,
            universe_version=handle.definition.universe_version,
        )
        market = query.market(
            members, start, end, price_policy=handle.definition.price_policy
        )
        qlib.init(
            provider_uri=str(cache),
            region="cn",
            expression_cache=None,
            dataset_cache=None,
            kernels=1,
        )
        qids = [to_qlib_instrument(ik).lower() for ik in members]
        fields = [f"${f}" for f in OHLCV_FIELDS]
        feat = D.features(
            qids,
            fields,
            start_time=str(min(market["trading_date"].tolist())),
            end_time=str(max(market["trading_date"].tolist())),
        )
        qlib_df = qlib_features_to_frame(feat, fields=OHLCV_FIELDS)
        market_keys = set(
            zip(
                market["instrument_key"].map(lambda x: to_qlib_instrument(str(x)).lower()),
                market["trading_date"].map(lambda d: d.date() if hasattr(d, "date") else d),
            )
        )
        qlib_df = qlib_df[
            qlib_df.apply(
                lambda r: (r["qlib_instrument"], r["trading_date"]) in market_keys,
                axis=1,
            )
        ].reset_index(drop=True)
        summary = compare_ohlcv_panels(market, qlib_df, fields=OHLCV_FIELDS)
        report["checks"]["ohlcv_panel"] = {"ok": True, **summary}
    except Exception as exc:
        fail("ohlcv_panel", {"error": str(exc)})

    # --- 3) PIT ---
    try:
        original_fundamental = query.fundamental

        def _spy_fundamental(*args, **kwargs):
            _spy_fundamental.called = True
            return original_fundamental(*args, **kwargs)

        _spy_fundamental.called = False
        query.fundamental = _spy_fundamental  # type: ignore[method-assign]
        mat.materialize(golden["dataset_ref"], force=True)
        if _spy_fundamental.called:
            raise RuntimeError("materializer called DataQuery.fundamental")
        query.fundamental = original_fundamental  # type: ignore[method-assign]

        kt_before = datetime(2024, 4, 29, 12, 0, tzinfo=timezone.utc)
        kt_after = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
        # golden synthetic ROE available_time=2024-04-30
        before = query.fundamental(["CNStock:000001"], ["ROE"], kt_before, exchange="CN")
        after = query.fundamental(["CNStock:000001"], ["ROE"], kt_after, exchange="CN")
        if not before.empty:
            raise RuntimeError("PIT leak: ROE visible before available_time")
        if after.empty:
            raise RuntimeError("PIT: ROE should be visible after available_time")
        panel = build_pit_safe_research_panel(
            query,
            ["CNStock:000001"],
            ["ROE"],
            kt_after,
            market_start=start,
            market_end=end,
        )
        if panel["ROE"].isna().all():
            raise RuntimeError("pit-safe panel missing ROE after KT")
        report["checks"]["pit"] = {
            "ok": True,
            "before_rows": int(len(before)),
            "after_rows": int(len(after)),
            "panel_roe": float(panel.iloc[0]["ROE"]),
        }
    except Exception as exc:
        fail("pit", {"error": str(exc)})
        # 确保还原
        try:
            query.fundamental = original_fundamental  # type: ignore[name-defined]
        except Exception:
            pass

    # --- 4) Universe survivor ---
    try:
        code = handle.definition.universe_code
        snap = handle.definition.snapshot_id
        ver = handle.definition.universe_version
        t1 = query.universe(code, date(2022, 6, 1), snapshot_id=snap, universe_version=ver)
        t2 = query.universe(code, end, snapshot_id=snap, universe_version=ver)
        if "CNStock:999999" not in t1 or "CNStock:999999" in t2:
            raise RuntimeError(f"survivor membership wrong: t1={t1} t2={t2}")
        if "CNStock:688001" not in t2:
            raise RuntimeError(f"late joiner missing at end: {t2}")
        file_ids = {
            ln.split("\t")[0]
            for ln in (cache / "instruments" / "all.txt").read_text(encoding="utf-8").splitlines()
            if ln.strip()
        }
        compare_universe_sets(t2, file_ids)
        report["checks"]["universe"] = {
            "ok": True,
            "t1_count": len(t1),
            "t2_count": len(t2),
            "t2": t2,
        }
    except Exception as exc:
        fail("universe", {"error": str(exc)})

    # --- 5) price_policy ---
    try:
        before_c = directory_sha256(Path(store.root))
        post_def = DatasetDefinition(
            code=GOLDEN_DATASET_CODE,
            version="v1_post_verify",
            name="post",
            frequency="1d",
            universe_code=handle.definition.universe_code,
            universe_version=handle.definition.universe_version,
            snapshot_id=handle.definition.snapshot_id,
            schema_version=handle.definition.schema_version,
            features=handle.definition.features,
            price_policy=PricePolicy(adjustment="post", return_type="price"),
            pit=True,
        )
        registry.upsert_dataset(post_def, status="validated")
        r_post = mat.materialize(f"{GOLDEN_DATASET_CODE}@v1_post_verify", force=True)
        after_c = directory_sha256(Path(store.root))
        assert_canonical_raw_unchanged(before_c, after_c)
        if result.dataset_hash == r_post.dataset_hash:
            raise RuntimeError("price_policy did not change dataset_hash")

        ik = "CNStock:000001"
        qid = to_qlib_instrument(ik).lower()
        m_none = query.market(
            [ik], date(2024, 1, 1), date(2024, 1, 31), price_policy=PricePolicy(adjustment="none")
        )
        m_post = query.market(
            [ik], date(2024, 1, 1), date(2024, 1, 31), price_policy=PricePolicy(adjustment="post")
        )
        if float(m_none.iloc[0]["close"]) == float(m_post.iloc[0]["close"]):
            raise RuntimeError("post adjustment did not change close")

        qlib.init(
            provider_uri=str(r_post.cache_path),
            region="cn",
            expression_cache=None,
            dataset_cache=None,
            kernels=1,
        )
        feat = D.features(
            [qid], ["$close"], start_time="2024-01-01", end_time="2024-01-31"
        )
        if feat.empty:
            raise RuntimeError("post D.features empty")
        report["checks"]["price_policy"] = {
            "ok": True,
            "none_hash": result.dataset_hash[:12],
            "post_hash": r_post.dataset_hash[:12],
            "canonical_unchanged": True,
        }
    except Exception as exc:
        fail("price_policy", {"error": str(exc)})

    # --- 6) hash rematerialize ---
    try:
        a = mat.materialize(golden["dataset_ref"], force=True)
        b = mat.materialize(golden["dataset_ref"], force=True)
        if a.dataset_hash != b.dataset_hash or a.checksum != b.checksum:
            raise RuntimeError("rematerialize hash/checksum unstable")
        report["checks"]["dataset_hash"] = {
            "ok": True,
            "dataset_hash": a.dataset_hash,
            "checksum": a.checksum,
            "materialization_id": a.materialization_id,
        }
    except Exception as exc:
        fail("dataset_hash", {"error": str(exc)})

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
