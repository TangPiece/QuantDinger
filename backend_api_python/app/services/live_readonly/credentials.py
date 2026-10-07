"""Phase 7A：Alpaca Live 凭证（仅 ALPACA_LIVE_*；host 白名单）。"""

from __future__ import annotations

import os
from typing import Optional

from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError

# Live REST 仅允许 production host
_LIVE_HOST_ALLOWLIST = frozenset(
    {
        "api.alpaca.markets",
        "https://api.alpaca.markets",
        "https://api.alpaca.markets/",
    }
)
_DEFAULT_LIVE_BASE = "https://api.alpaca.markets"


def _normalize_host(base_url: str) -> str:
    b = str(base_url or "").strip().rstrip("/")
    host = b.lower().replace("https://", "").replace("http://", "").split("/")[0]
    return host


def load_alpaca_live_credentials() -> dict[str, str]:
    """读取 ALPACA_LIVE_*；拒绝 paper host 与非白名单。"""
    key = (os.environ.get("ALPACA_LIVE_API_KEY") or "").strip()
    secret = (os.environ.get("ALPACA_LIVE_API_SECRET") or "").strip()
    base = (
        os.environ.get("ALPACA_LIVE_BASE_URL") or _DEFAULT_LIVE_BASE
    ).strip().rstrip("/")

    host = _normalize_host(base)
    if "paper-api" in host or host.startswith("paper-"):
        raise BrokerAdapterError(
            "Alpaca Paper host forbidden for ALPACA_LIVE_*",
            code=AdapterErrorCode.LIVE_FORBIDDEN,
        )
    if host != "api.alpaca.markets":
        raise BrokerAdapterError(
            f"ALPACA_LIVE_BASE_URL must be api.alpaca.markets, got {base!r}",
            code=AdapterErrorCode.LIVE_FORBIDDEN,
        )
    return {
        "api_key": key,
        "api_secret": secret,
        "base_url": base,
    }


def has_alpaca_live_credentials() -> bool:
    """是否配置了 Live 凭证（不校验 PRODUCTION_READY）。"""
    try:
        c = load_alpaca_live_credentials()
    except BrokerAdapterError:
        return False
    return bool(c["api_key"] and c["api_secret"])


def env_or_none(name: str) -> Optional[str]:
    v = (os.environ.get(name) or "").strip()
    return v or None
