"""Phase 7A：session / snapshot 派生 id。"""

from __future__ import annotations

import hashlib


def derive_session_id(
    *,
    account_id: str,
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    salt: str = "",
) -> str:
    """会话 id：绑定账户与三版本。"""
    raw = "|".join(
        [
            account_id,
            dataset_hash,
            model_version,
            strategy_version,
            salt,
        ]
    )
    return "lro_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
