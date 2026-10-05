"""Backtest artifact 落盘：qd/artifacts/backtest/{result_id}/。"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.research_data import config as rd_config
from app.services.research_data.backtest.result import BacktestResult
from app.services.research_data.contracts import ArtifactRecord

from .version import QLIB_BACKTEST_ENGINE_VERSION


def backtest_artifact_root(root: Path | None = None) -> Path:
    """{research_cache}/qd/artifacts/backtest。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "artifacts" / "backtest"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_result_id(request_fingerprint: str, engine_version: str = QLIB_BACKTEST_ENGINE_VERSION) -> str:
    """内容寻址 result_id（短 hex）。"""
    payload = f"{request_fingerprint}|{engine_version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass
class BacktestArtifactStore:
    """写入 result.json + 可选 equity/trades parquet。"""

    root: Path | None = None

    def dir_for(self, result_id: str) -> Path:
        return backtest_artifact_root(self.root) / result_id

    def write_result(
        self,
        result: BacktestResult,
        *,
        report: pd.DataFrame | None = None,
    ) -> ArtifactRecord:
        """落盘 BacktestResult；返回 Registry ArtifactRecord。"""
        dest = self.dir_for(result.result_id)
        dest.mkdir(parents=True, exist_ok=True)

        result_path = dest / "result.json"
        payload = result.model_dump(mode="json")
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        result_path.write_text(text, encoding="utf-8")

        uris: dict[str, str] = {"result": str(result_path.resolve())}
        blobs: list[bytes] = [text.encode("utf-8")]

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
            eq_path = dest / "equity.parquet"
            eq_bytes = _df_parquet_bytes(eq_df)
            eq_path.write_bytes(eq_bytes)
            uris["equity"] = str(eq_path.resolve())
            blobs.append(eq_bytes)

        if result.trades:
            tr_df = pd.DataFrame([t.model_dump(mode="json") for t in result.trades])
            tr_path = dest / "trades.parquet"
            tr_bytes = _df_parquet_bytes(tr_df)
            tr_path.write_bytes(tr_bytes)
            uris["trades"] = str(tr_path.resolve())
            blobs.append(tr_bytes)

        if report is not None and not report.empty:
            rp_path = dest / "qlib_report.parquet"
            rp_bytes = _df_parquet_bytes(report.reset_index())
            rp_path.write_bytes(rp_bytes)
            uris["qlib_report"] = str(rp_path.resolve())
            blobs.append(rp_bytes)

        # 回写 artifact_uris 到 result.json
        result.artifact_uris = uris
        result_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        checksum = hashlib.sha256(b"".join(blobs)).hexdigest()
        size_bytes = sum(len(b) for b in blobs)
        return ArtifactRecord(
            artifact_id=result.result_id,
            artifact_type="backtest",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=size_bytes,
            metadata={
                "engine": result.engine,
                "engine_version": result.engine_version,
                "request_fingerprint": result.request_fingerprint,
                "experiment_id": result.experiment_id,
            },
        )


def _df_parquet_bytes(df: pd.DataFrame) -> bytes:
    """DataFrame → parquet bytes。"""
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()
