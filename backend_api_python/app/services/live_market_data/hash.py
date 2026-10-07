"""Phase 7B：Live MD session / batch id。"""

from __future__ import annotations

import hashlib


def derive_md_session_id(
    *,
    feed_id: str,
    account_id: str,
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    salt: str = "",
) -> str:
    raw = "|".join(
        [feed_id, account_id, dataset_hash, model_version, strategy_version, salt]
    )
    return "lmd_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def derive_event_batch_id(*, session_id: str, seq: int) -> str:
    raw = f"{session_id}|{seq}"
    return "lmdb_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
