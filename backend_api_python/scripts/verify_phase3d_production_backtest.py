#!/usr/bin/env python3
"""Phase 3D 验收：Production Backtest 引擎（无 qlib）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 python scripts/verify_phase3d_production_backtest.py
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

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.research_data.backtest.execution.models import MarketBar
    from app.services.research_data.backtest.fingerprint import compute_request_fingerprint
    from app.services.research_data.backtest.presets import cn_equity_close_signal_next_open
    from app.services.research_data.backtest.request import BacktestRequest
    from app.services.research_data.backtest_production import (
        PRODUCTION_BACKTEST_ENGINE_VERSION,
        ProductionArtifactStore,
        ProductionBacktestEngine,
    )
    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.contracts import ExperimentDefinition, TargetPosition
    from app.services.research_data.data_query import DataQuery
    from app.services.research_data.registry import LocalJsonRegistry

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase3d_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")

    store = LocalCanonicalStore(root=tmp / "canonical")
    registry = LocalJsonRegistry(root=tmp / "registry")
    query = DataQuery(store, registry)
    registry.upsert_experiment(
        ExperimentDefinition(
            experiment_id="exp_3d_verify",
            name="phase3d verify",
            dataset_ref="dummy@1",
            snapshot_id="snap_3d_verify",
            dataset_hash="ds_hash_3d_verify",
            strategy_version="verify@1",
            signal_artifact_id="sig_art_verify",
        )
    )

    eng = ProductionBacktestEngine(
        query,
        registry,
        artifact_store=ProductionArtifactStore(root=tmp / "bt_art"),
    )

    ik = "CNStock:600519"
    days = ["2024-05-06", "2024-05-07", "2024-05-08"]

    def bar(day: str, **kw) -> MarketBar:
        raw = dict(
            instrument_key=ik,
            trading_date=day,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1e6,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=False,
        )
        raw.update(kw)
        return MarketBar(**raw)

    bars = {d: {ik: bar(d, open=100.0)} for d in days}
    target = TargetPosition(
        instrument_key=ik,
        trading_date="2024-05-06",
        portfolio_id="p1",
        strategy_version="verify@1",
        dataset_hash="ds_hash_3d_verify",
        timestamp=datetime(2024, 5, 6, 15, 0, 0, tzinfo=timezone.utc),
        target_quantity=100.0,
        target_weight=0.0,
        signal_id="sig_verify",
    )

    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    req = BacktestRequest(
        experiment_id="exp_3d_verify",
        dataset_hash="ds_hash_3d_verify",
        strategy_version="verify@1",
        start_date="2024-05-06",
        end_date="2024-05-08",
        initial_capital=1_000_000.0,
        engine="production",
        execution_policy=exec_p,
        market_price_policy=price_p,
        cost_policy=cost_p,
        trading_rule=rules,
        target_positions_artifact_id="sig_art_verify",
    )

    # 1) 无交易
    empty = eng.run(req, bars_by_date=bars, targets_by_date={})
    no_trade_ok = abs(empty.equity_curve[-1].equity - 1_000_000.0) < 1e-6

    # 2) 单次买入（T+1 open）
    bought = eng.run(
        req,
        bars_by_date=bars,
        targets_by_date={"2024-05-06": [target]},
    )
    filled = [
        t
        for t in bought.trades
        if t.status in ("FILLED", "PARTIAL") and t.side == "BUY" and t.quantity > 0
    ]
    buy_ok = bool(filled) and filled[0].quantity == 100.0

    # 3) 涨停拒买
    bars_lu = {
        "2024-05-06": {ik: bar("2024-05-06")},
        "2024-05-07": {ik: bar("2024-05-07", open=110.0, is_limit_up=True)},
        "2024-05-08": {ik: bar("2024-05-08")},
    }
    blocked = eng.run(
        req,
        bars_by_date=bars_lu,
        targets_by_date={"2024-05-06": [target]},
    )
    limit_ok = not any(
        t.status in ("FILLED", "PARTIAL") and t.quantity > 0 for t in blocked.trades
    )

    # 4) 确定性双跑
    a = eng.run(req, bars_by_date=bars, targets_by_date={"2024-05-06": [target]})
    b = eng.run(req, bars_by_date=bars, targets_by_date={"2024-05-06": [target]})
    det_ok = (
        a.request_fingerprint == b.request_fingerprint == compute_request_fingerprint(req)
        and a.result_id == b.result_id
        and abs(a.equity_curve[-1].equity - b.equity_curve[-1].equity) < 1e-6
    )

    # 5) artifact / manifest
    man_uri = a.artifact_uris.get("manifest")
    manifest_ok = False
    if man_uri and Path(man_uri).is_file():
        man = json.loads(Path(man_uri).read_text(encoding="utf-8"))
        manifest_ok = (
            man.get("engine") == "production"
            and man.get("engine_version") == PRODUCTION_BACKTEST_ENGINE_VERSION
            and "checksum" in man
        )

    checks = {
        "no_trade_equity": no_trade_ok,
        "single_buy_fill": buy_ok,
        "limit_up_blocked": limit_ok,
        "determinism": det_ok,
        "manifest": manifest_ok,
        "engine_version": a.engine_version == PRODUCTION_BACKTEST_ENGINE_VERSION,
    }
    all_ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": all_ok,
                "checks": checks,
                "result_id": a.result_id,
                "final_equity": a.equity_curve[-1].equity if a.equity_curve else None,
                "tmp": str(tmp),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
