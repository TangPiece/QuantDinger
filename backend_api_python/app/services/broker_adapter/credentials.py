"""凭证仅从环境变量读取；禁止写入 D1/R2/Order.metadata。"""

from __future__ import annotations

import os
from typing import Optional

from .errors import AdapterErrorCode, BrokerAdapterError


# Alpaca Paper 默认 endpoint（禁止 live host）
_ALPACA_PAPER_HOSTS = frozenset(
    {
        "https://paper-api.alpaca.markets",
        "https://paper-api.alpaca.markets/",
        "paper-api.alpaca.markets",
    }
)
_ALPACA_LIVE_MARKERS = ("api.alpaca.markets", "live")


def load_alpaca_paper_credentials() -> dict[str, str]:
    """读取 ALPACA_PAPER_*；拒绝 live host。"""
    key = (os.environ.get("ALPACA_PAPER_API_KEY") or "").strip()
    secret = (os.environ.get("ALPACA_PAPER_API_SECRET") or "").strip()
    base = (
        os.environ.get("ALPACA_PAPER_BASE_URL") or "https://paper-api.alpaca.markets"
    ).strip().rstrip("/")
    data_url = (
        os.environ.get("ALPACA_PAPER_DATA_URL") or "https://data.alpaca.markets"
    ).strip().rstrip("/")

    host = base.lower().replace("https://", "").replace("http://", "").split("/")[0]
    # 明确拒绝 live trading host（paper-api 合法）
    if host == "api.alpaca.markets" or host.startswith("api.alpaca.markets:"):
        raise BrokerAdapterError(
            "Alpaca Live host forbidden in Phase 6E",
            code=AdapterErrorCode.LIVE_FORBIDDEN,
        )
    if "paper" not in host and host not in {h.replace("https://", "").rstrip("/") for h in _ALPACA_PAPER_HOSTS}:
        raise BrokerAdapterError(
            f"ALPACA_PAPER_BASE_URL must be paper endpoint, got {base!r}",
            code=AdapterErrorCode.LIVE_FORBIDDEN,
        )
    return {
        "api_key": key,
        "api_secret": secret,
        "base_url": base,
        "data_url": data_url,
    }


def has_alpaca_paper_credentials() -> bool:
    c = load_alpaca_paper_credentials()
    return bool(c["api_key"] and c["api_secret"])


def env_or_none(name: str) -> Optional[str]:
    v = (os.environ.get(name) or "").strip()
    return v or None
