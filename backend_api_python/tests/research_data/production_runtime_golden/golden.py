"""Phase 6A Golden：DEPLOYED Bundle → PAPER tick → OrderIntent。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.services.production_runtime import ProductionRuntimeService
from app.services.research_data.production_bridge import ProductionBridgeService

# 复用 5F golden 环境
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from production_bridge_golden.golden import (  # noqa: E402
    INST_A,
    INST_B,
    factor_rows,
    make_env as make_bridge_env,
    price_bars,
    promote_to_deployed,
    trading_days,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def make_env(tmp: Path):
    store, registry, bridge = make_bridge_env(tmp)
    rt = ProductionRuntimeService(store, registry, bridge=bridge)
    return store, registry, bridge, rt


def deployed_bundle(bridge: ProductionBridgeService, days: list[date] | None = None):
    return promote_to_deployed(bridge, days)


def intraday_now(day: date, hour: int = 10, minute: int = 30) -> datetime:
    """构造 CN_A 日内时间（Asia/Shanghai）。"""
    return datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=SHANGHAI
    ).astimezone(timezone.utc)


def tick_meta(day: date, *, force_new_run: bool = False) -> dict[str, Any]:
    days = [day]
    return {
        "trading_date": day.isoformat(),
        "session_phase": "INTRADAY",
        "decision_bucket": "INTRADAY_TEST",
        "force_intraday": True,
        "force_new_run": force_new_run,
        "factor_rows": factor_rows(days),
        "price_bars": price_bars(days),
        "universe_membership": [INST_A, INST_B],
        "instruments": [INST_A, INST_B],
        "max_single_weight": 1.0,
        "max_gross_exposure": 1.0,
    }
