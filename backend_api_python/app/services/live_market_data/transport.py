"""Phase 7B：Alpaca Data GET-only；Fake transport 供 CI。"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError, redact_secrets

from .credentials import load_alpaca_live_data_credentials

# 写路径硬禁（AST/测试也会扫描）
_FORBIDDEN_ORDER_WRITE_PATHS = frozenset({"/v2/orders"})


class AlpacaLiveMdTransport:
    """Alpaca Data REST：仅 GET quotes/bars；永不 POST /v2/orders。"""

    def __init__(self, credentials: Mapping[str, str] | None = None) -> None:
        creds = dict(credentials or load_alpaca_live_data_credentials())
        if not creds.get("api_key") or not creds.get("api_secret"):
            raise BrokerAdapterError(
                "ALPACA_LIVE_API_KEY/SECRET required for data",
                code=AdapterErrorCode.AUTH_FAILED,
            )
        self.data_url = str(creds["data_url"]).rstrip("/")
        self._key = creds["api_key"]
        self._secret = creds["api_secret"]

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "Accept": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = 30.0,
    ) -> Any:
        """仅允许 GET；订单写路径一律拒绝。"""
        m = method.upper()
        if m != "GET":
            raise BrokerAdapterError(
                f"LIVE_MD: HTTP {m} forbidden",
                code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
            )
        p = path.split("?", 1)[0].rstrip("/")
        if p in _FORBIDDEN_ORDER_WRITE_PATHS:
            raise BrokerAdapterError(
                "LIVE_MD: POST /v2/orders forbidden",
                code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
            )

        url = f"{self.data_url}{path}"
        req = Request(url, headers=self._headers(), method="GET")
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = str(exc)
            raise BrokerAdapterError(
                redact_secrets(f"alpaca data HTTP {exc.code}: {detail}"),
                code=AdapterErrorCode.REJECTED
                if exc.code in (400, 403, 422)
                else AdapterErrorCode.NETWORK_UNKNOWN,
            ) from exc
        except URLError as exc:
            raise BrokerAdapterError(
                redact_secrets(f"alpaca data network: {exc}"),
                code=AdapterErrorCode.NETWORK_UNKNOWN,
            ) from exc

    def get_latest_quote(self, symbol: str, *, feed: str = "iex") -> dict[str, Any]:
        sym = quote(str(symbol).upper(), safe="")
        return self.request("GET", f"/v2/stocks/{sym}/quotes/latest?feed={feed}")

    def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str = "1Min",
        start: str = "",
        end: str = "",
        limit: int = 100,
        feed: str = "iex",
    ) -> dict[str, Any]:
        sym = quote(str(symbol).upper(), safe="")
        q = f"/v2/stocks/{sym}/bars?timeframe={timeframe}&limit={limit}&feed={feed}"
        if start:
            q += f"&start={quote(start, safe='')}"
        if end:
            q += f"&end={quote(end, safe='')}"
        return self.request("GET", q)


class FakeLiveMdTransport:
    """测试用内存 transport；不触网。"""

    def __init__(
        self,
        *,
        quotes: Mapping[str, Mapping[str, Any]] | None = None,
        bars: Mapping[str, list[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.data_url = "https://data.alpaca.markets"
        self._quotes = {k.upper(): dict(v) for k, v in (quotes or {}).items()}
        self._bars = {k.upper(): [dict(b) for b in v] for k, v in (bars or {}).items()}

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if method.upper() != "GET":
            raise BrokerAdapterError(
                f"LIVE_MD: HTTP {method} forbidden",
                code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
            )
        if method.upper() == "POST" and "/v2/orders" in path:
            raise BrokerAdapterError(
                "LIVE_MD: POST /v2/orders forbidden",
                code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
            )
        if "/quotes/latest" in path:
            sym = path.split("/stocks/", 1)[-1].split("/")[0].upper()
            return {"quote": self._quotes.get(sym, self._default_quote(sym))}
        if "/bars" in path:
            sym = path.split("/stocks/", 1)[-1].split("/")[0].upper()
            return {"bars": self._bars.get(sym, [])}
        return {}

    def _default_quote(self, symbol: str) -> dict[str, Any]:
        return {
            "ap": 100.05,
            "bp": 99.95,
            "as": 100,
            "bs": 100,
            "t": "2020-01-01T15:00:00Z",
        }

    def get_latest_quote(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", f"/v2/stocks/{symbol.upper()}/quotes/latest")

    def get_bars(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", f"/v2/stocks/{symbol.upper()}/bars")
