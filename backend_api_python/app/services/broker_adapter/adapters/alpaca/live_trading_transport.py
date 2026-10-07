"""Phase 7C：Alpaca Live Trading REST — 仅 POST submit + GET 查询；禁 DELETE/PATCH。"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.live_readonly.credentials import load_alpaca_live_credentials

from ...errors import AdapterErrorCode, BrokerAdapterError, redact_secrets

_FORBIDDEN_METHODS = frozenset({"DELETE", "PATCH", "PUT"})


class AlpacaLiveTradingTransport:
    """Live host 写路径最小面：只开放 submit 与 by_client_order_id。"""

    def __init__(self, credentials: Mapping[str, str] | None = None) -> None:
        creds = dict(credentials or load_alpaca_live_credentials())
        if not creds.get("api_key") or not creds.get("api_secret"):
            raise BrokerAdapterError(
                "ALPACA_LIVE_API_KEY/SECRET required for controlled submit",
                code=AdapterErrorCode.AUTH_FAILED,
            )
        self.base_url = str(creds["base_url"]).rstrip("/")
        self._key = creds["api_key"]
        self._secret = creds["api_secret"]

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        m = method.upper()
        if m in _FORBIDDEN_METHODS:
            raise BrokerAdapterError(
                f"method {m} forbidden in Phase 7C controlled live",
                code=AdapterErrorCode.LIVE_FORBIDDEN,
            )
        url = f"{self.base_url}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method=m)
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
                redact_secrets(f"alpaca live HTTP {exc.code}: {detail}"),
                code=AdapterErrorCode.REJECTED
                if exc.code in (400, 403, 422)
                else AdapterErrorCode.NETWORK_UNKNOWN,
            ) from exc
        except URLError as exc:
            raise BrokerAdapterError(
                redact_secrets(f"alpaca live network: {exc}"),
                code=AdapterErrorCode.NETWORK_UNKNOWN,
            ) from exc

    def submit_order(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/v2/orders", body=dict(payload))

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/v2/orders:by_client_order_id?client_order_id={client_order_id}",
        )

    def get_order(self, broker_order_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v2/orders/{broker_order_id}")
