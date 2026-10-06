"""Production Backtest artifact：result.json + manifest + parquet。"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.research_data import config as rd_config
from app.services.research_data.backtest.request import BacktestRequest
from app.services.research_data.backtest.result import BacktestResult
from app.services.research_data.contracts import ArtifactRecord

from .version import PRODUCTION_BACKTEST_ENGINE_VERSION


def backtest_artifact_root(root: Path | None = None) -> Path:
    """{research_cache}/qd/artifacts/backtest。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "artifacts" / "backtest"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_result_id(
    request_fingerprint: str,
    engine_version: str = PRODUCTION_BACKTEST_ENGINE_VERSION,
) -> str:
    """内容寻址 result_id。"""
    payload = f"{request_fingerprint}|{engine_version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _df_parquet_bytes(df: pd.DataFrame) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


@dataclass
class ProductionArtifactStore:
    """写入 result / manifest / equity / trades / positions。"""

    root: Path | None = None

    def dir_for(self, result_id: str) -> Path:
        return backtest_artifact_root(self.root) / result_id

    def write_result(
        self,
        result: BacktestResult,
        *,
        request: BacktestRequest | None = None,
        snapshot_id: str | None = None,
        extra_manifest: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        """落盘并回写 result.artifact_uris。"""
        dest = self.dir_for(result.result_id)
        dest.mkdir(parents=True, exist_ok=True)
        uris: dict[str, str] = {}
        blobs: list[bytes] = []

        result_path = dest / "result.json"
        result_text = json.dumps(
            result.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str
        )
        result_path.write_text(result_text, encoding="utf-8")
        uris["result"] = str(result_path.resolve())
        blobs.append(result_text.encode("utf-8"))

        if result.equity_curve:
            eq_df = pd.DataFrame(
                [
                    {
                        "trading_date": p.trading_date,
                        "equity": p.equity,
                        "drawdown": p.drawdown,
                    }
                    for p in result.equity_curve
                ]
            )
            eq_bytes = _df_parquet_bytes(eq_df)
            eq_path = dest / "equity.parquet"
            eq_path.write_bytes(eq_bytes)
            uris["equity"] = str(eq_path.resolve())
            blobs.append(eq_bytes)

        if result.trades:
            tr_bytes = _df_parquet_bytes(
                pd.DataFrame([t.model_dump(mode="json") for t in result.trades])
            )
            tr_path = dest / "trades.parquet"
            tr_path.write_bytes(tr_bytes)
            uris["trades"] = str(tr_path.resolve())
            blobs.append(tr_bytes)

        if result.position_history:
            pos_bytes = _df_parquet_bytes(
                pd.DataFrame([p.model_dump(mode="json") for p in result.position_history])
            )
            pos_path = dest / "positions.parquet"
            pos_path.write_bytes(pos_bytes)
            uris["positions"] = str(pos_path.resolve())
            blobs.append(pos_bytes)

        manifest = {
            "result_id": result.result_id,
            "experiment_id": result.experiment_id,
            "dataset_hash": result.dataset_hash,
            "engine": result.engine,
            "engine_version": result.engine_version,
            "contract_version": result.contract_version,
            "request_fingerprint": result.request_fingerprint,
            "snapshot_id": snapshot_id,
            "start": request.start_date if request else None,
            "end": request.end_date if request else None,
            "initial_capital": request.initial_capital if request else None,
            "price_policy": (
                request.market_price_policy.model_dump(mode="json") if request else None
            ),
            "execution_policy": (
                request.execution_policy.model_dump(mode="json") if request else None
            ),
            "cost_policy": request.cost_policy.model_dump(mode="json") if request else None,
            "trading_rules": (
                request.trading_rule.model_dump(mode="json") if request else None
            ),
            "artifacts": list(uris.keys()),
        }
        if extra_manifest:
            manifest.update(extra_manifest)
        man_text = json.dumps(manifest, ensure_ascii=False, indent=2, default=str)
        man_path = dest / "manifest.json"
        man_path.write_text(man_text, encoding="utf-8")
        uris["manifest"] = str(man_path.resolve())
        blobs.append(man_text.encode("utf-8"))

        checksum = hashlib.sha256(b"".join(blobs)).hexdigest()
        manifest["checksum"] = checksum
        man_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        result.artifact_uris = uris
        result_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        return ArtifactRecord(
            artifact_id=result.result_id,
            artifact_type="backtest",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=sum(len(b) for b in blobs),
            metadata={
                "engine": result.engine,
                "engine_version": result.engine_version,
                "request_fingerprint": result.request_fingerprint,
                "experiment_id": result.experiment_id,
            },
        )
