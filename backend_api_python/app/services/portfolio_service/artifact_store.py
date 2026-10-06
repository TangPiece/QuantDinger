"""Portfolio 本地产物（snapshot / events）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.paths import (
    production_portfolio_event_key,
    production_portfolio_prefix,
    production_portfolio_snapshot_key,
)

from .protocol import ENGINE_VERSION, PortfolioSnapshot, PositionEvent


def portfolio_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "production" / "portfolio"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class PortfolioArtifactStore:
    """写 portfolio snapshot / events 到本地 cache。"""

    root: Path | None = None

    def dir_for(self, account_id: str, trading_date: str = "") -> Path:
        base = portfolio_root(self.root) / f"account={account_id}"
        if trading_date:
            try:
                d = date.fromisoformat(trading_date[:10])
                base = base / f"year={d.year:04d}" / f"month={d.month:02d}" / f"day={d.day:02d}"
            except Exception:
                pass
        base.mkdir(parents=True, exist_ok=True)
        return base

    def write_snapshot(self, snapshot: PortfolioSnapshot) -> str:
        dest = self.dir_for(snapshot.account_id, snapshot.trading_date)
        payload = {
            "engine_version": ENGINE_VERSION,
            "snapshot": snapshot.model_dump(mode="json"),
            "r2_key": _snap_key(snapshot),
        }
        path = dest / "portfolio.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        # positions / pnl 分文件（parquet 占位用 json，避免强依赖 pyarrow 写路径）
        (dest / "positions.json").write_text(
            json.dumps(
                [p.model_dump(mode="json") for p in snapshot.positions],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (dest / "pnl.json").write_text(
            json.dumps(
                {
                    "realized_pnl": snapshot.realized_pnl,
                    "unrealized_pnl": snapshot.unrealized_pnl,
                    "total_pnl": snapshot.total_pnl,
                    "fees": snapshot.fees,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return str(dest)

    def write_event(self, account_id: str, event: PositionEvent) -> Path:
        dest = self.dir_for(account_id, event.trading_date) / "events"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{event.event_id}.json"
        path.write_text(
            json.dumps(event.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def _snap_key(snapshot: PortfolioSnapshot) -> str:
    try:
        d = date.fromisoformat(snapshot.trading_date[:10])
        return production_portfolio_snapshot_key(
            account_id=snapshot.account_id,
            year=d.year,
            month=d.month,
            day=d.day,
        )
    except Exception:
        return production_portfolio_prefix(account_id=snapshot.account_id)
