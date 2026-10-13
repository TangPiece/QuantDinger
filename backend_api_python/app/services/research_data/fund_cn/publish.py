"""Publish daily fund_cn factor panels to local cache + R2 Canonical factor tree."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.research_data import paths as research_paths
from app.services.research_data.canonical_store import CanonicalStore, LocalCanonicalStore
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.contracts import FactorDatasetRecord
from app.services.research_data.factor_lab.dataset import compute_factor_dataset_id
from app.services.research_data.factor_lab.hash import compute_factor_hash
from app.services.research_data.contracts import FeatureDefinition

from .catalog import FACTOR_SET, FACTOR_VERSION, schema_hash
from .paths_local import default_factor_root, local_factor_day_path, r2_factor_set
from .staging import write_marker

_log = logging.getLogger(__name__)


def write_local_day(root: Path, trading_date: str, frame: pd.DataFrame) -> Path:
    day = str(trading_date).replace("-", "")
    dest = local_factor_day_path(root, day)
    temporary = dest.with_suffix(".parquet.tmp")
    panel = frame.copy()
    if "trading_date" not in panel.columns:
        panel["trading_date"] = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
    panel.to_parquet(temporary, index=False)
    temporary.replace(dest)
    return dest


def upload_day_to_store(
    store: CanonicalStore,
    trading_date: str,
    frame: pd.DataFrame,
    *,
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    day = str(trading_date).replace("-", "")
    y = year or int(day[:4])
    m = month or int(day[4:6])
    key = research_paths.factor_daily_key(
        factor_set=r2_factor_set(),
        year=y,
        month=m,
        part=f"{day}.parquet",
    )
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(frame, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    payload = buf.getvalue()
    checksum = hashlib.sha256(payload).hexdigest()
    try:
        store.put_bytes(key, payload)
        uploaded = True
    except Exception as exc:
        _log.warning("fund_cn R2/local store upload soft-fail %s: %s", key, exc)
        uploaded = False
    return {
        "storage_uri": key,
        "checksum": checksum,
        "row_count": int(len(frame)),
        "uploaded": uploaded,
    }


def register_dataset_soft(
    registry: ResearchRegistry | None,
    *,
    storage_uri: str,
    checksum: str,
    row_count: int,
    start_date: str,
    end_date: str,
    snapshot_id: str = "fund_cn_local",
) -> str | None:
    """Soft-fail FactorDataset registration into research registry (D1 or local)."""
    if registry is None:
        return None
    try:
        feature = FeatureDefinition(
            code="fund_cn_basic",
            version="1.0.0",
            name="CN fundamental basic set",
            expression="fund_cn_basic_panel",
            factor_type="FUNDAMENTAL",
            information_policy="PIT_SAFE",
            dependencies=["fundamental:roe"],
            schema_version="factor_daily_wide@1",
        )
        feature = feature.model_copy(update={"factor_hash": compute_factor_hash(feature)})
        dataset_hash = hashlib.sha256(
            f"{FACTOR_SET}|{schema_hash()}|{start_date}|{end_date}|{checksum}".encode()
        ).hexdigest()[:32]
        factor_dataset_id = compute_factor_dataset_id(
            factor_hash=feature.factor_hash or "",
            dataset_hash=dataset_hash,
            snapshot_id=snapshot_id,
            universe_code="CN",
            frequency="1d",
            start_date=start_date,
            end_date=end_date,
            layout="wide",
        )
        record = FactorDatasetRecord(
            factor_dataset_id=factor_dataset_id,
            factor_ref=feature.code + "@" + feature.version,
            factor_hash=feature.factor_hash or "",
            dataset_hash=dataset_hash,
            snapshot_id=snapshot_id,
            universe_code="CN",
            frequency="1d",
            start_date=start_date,
            end_date=end_date,
            storage_uri=storage_uri,
            checksum=checksum,
            row_count=row_count,
            layout="wide",
            schema_version="factor_daily_wide@1",
            status="ACTIVE",
            metadata={
                "factor_set": FACTOR_SET,
                "factor_version": FACTOR_VERSION,
                "schema_hash": schema_hash(),
            },
        )
        registry.upsert_factor_dataset(record)
        return factor_dataset_id
    except Exception as exc:
        _log.warning("fund_cn registry soft-fail: %s", exc)
        return None


def publish_day_panel(
    frame: pd.DataFrame,
    trading_date: str,
    *,
    store: CanonicalStore | None = None,
    factor_root: Path | None = None,
    registry: ResearchRegistry | None = None,
    upload: bool = True,
) -> dict[str, Any]:
    root = factor_root or default_factor_root()
    local_path = write_local_day(root, trading_date, frame)
    result: dict[str, Any] = {
        "trading_date": trading_date,
        "local_path": str(local_path),
        "row_count": int(len(frame)),
    }
    if upload:
        canonical = store or LocalCanonicalStore()
        remote = upload_day_to_store(canonical, trading_date, frame)
        result.update(remote)
        day = str(trading_date).replace("-", "")
        iso = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        dataset_id = register_dataset_soft(
            registry,
            storage_uri=str(remote.get("storage_uri") or ""),
            checksum=str(remote.get("checksum") or ""),
            row_count=int(remote.get("row_count") or 0),
            start_date=iso,
            end_date=iso,
        )
        result["factor_dataset_id"] = dataset_id
    write_marker(
        f"factor_{str(trading_date).replace('-', '')}",
        {"status": "done", **{k: v for k, v in result.items() if k != "local_path"}},
        root=None,
    )
    return result
