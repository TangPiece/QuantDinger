"""Phase 7B：Alpaca Data 凭证（ALPACA_LIVE_* + data host 白名单）。"""

from __future__ import annotations

import os
from typing import Optional

from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError

# Data REST / 可选 stream host（与 Trading 同钥）
_DATA_HOST_ALLOWLIST = frozenset(
    {
        "data.alpaca.markets",
        "stream.data.alpaca.markets",
    }
)
_DEFAULT_DATA_BASE = "https://data.alpaca.markets"
_DEFAULT_STREAM_HOST = "wss://stream.data.alpaca.markets/v2/iex"


def _normalize_host(url: str) -> str:
    b = str(url or "").strip().rstrip("/")
    host = b.lower().replace("https://", "").replace("http://", "").replace("wss://", "").replace("ws://", "")
    return host.split("/")[0]


def load_alpaca_live_data_credentials() -> dict[str, str]:
    """读取 ALPACA_LIVE_*；data host 必须在白名单内。"""
    key = (os.environ.get("ALPACA_LIVE_API_KEY") or "").strip()
    secret = (os.environ.get("ALPACA_LIVE_API_SECRET") or "").strip()
    data_base = (
        os.environ.get("ALPACA_LIVE_DATA_URL") or _DEFAULT_DATA_BASE
    ).strip().rstrip("/")
    stream = (
        os.environ.get("ALPACA_LIVE_STREAM_URL") or _DEFAULT_STREAM_HOST
    ).strip()

    data_host = _normalize_host(data_base)
    stream_host = _normalize_host(stream)
    if data_host not in _DATA_HOST_ALLOWLIST:
        raise BrokerAdapterError(
            f"ALPACA_LIVE_DATA_URL host must be in {_DATA_HOST_ALLOWLIST}, got {data_base!r}",
            code=AdapterErrorCode.LIVE_FORBIDDEN,
        )
    if stream_host and stream_host not in _DATA_HOST_ALLOWLIST:
        raise BrokerAdapterError(
            f"ALPACA_LIVE_STREAM_URL host must be in {_DATA_HOST_ALLOWLIST}, got {stream!r}",
            code=AdapterErrorCode.LIVE_FORBIDDEN,
        )
    return {
        "api_key": key,
        "api_secret": secret,
        "data_url": data_base,
        "stream_url": stream,
    }


def has_alpaca_live_data_credentials() -> bool:
    try:
        c = load_alpaca_live_data_credentials()
    except BrokerAdapterError:
        return False
    return bool(c["api_key"] and c["api_secret"])


def env_or_none(name: str) -> Optional[str]:
    v = (os.environ.get(name) or "").strip()
    return v or None
