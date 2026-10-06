"""OMS Artifact：order / events / fills → local 或 R2 路径。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.services.research_data import paths as rd_paths

from .protocol import Fill, Order, OrderEvent


class OmsArtifactStore:
    """写 ``qd/production/oms/{order_id}/``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def _local_dir(self, order_id: str) -> Path:
        base = self.root or Path(
            __import__("tempfile").gettempdir()
        ) / "qd_oms_artifacts"
        d = base / "production" / "oms" / order_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_order(self, order: Order) -> str:
        key = rd_paths.production_oms_order_key(order_id=order.order_id)
        if self.root is not None:
            path = self._local_dir(order.order_id) / "order.json"
            path.write_text(
                json.dumps(order.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return str(path)
        return rd_paths.r2_uri(key)

    def write_event(self, event: OrderEvent) -> str:
        key = (
            f"{rd_paths.production_oms_prefix(order_id=event.order_id, kind='events')}"
            f"/{event.event_id}.json"
        )
        if self.root is not None:
            path = self._local_dir(event.order_id) / "events"
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{event.event_id}.json"
            fp.write_text(
                json.dumps(event.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return str(fp)
        return rd_paths.r2_uri(key)

    def write_fill(self, fill: Fill) -> str:
        key = (
            f"{rd_paths.production_oms_prefix(order_id=fill.order_id, kind='fills')}"
            f"/{fill.fill_id}.json"
        )
        if self.root is not None:
            path = self._local_dir(fill.order_id) / "fills"
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{fill.fill_id}.json"
            fp.write_text(
                json.dumps(fill.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return str(fp)
        return rd_paths.r2_uri(key)
