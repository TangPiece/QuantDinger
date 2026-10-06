"""Alpaca Paper 纯 HTTP transport；禁止复用 live_trading Domain。"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ...credentials import load_alpaca_paper_credentials
from ...errors import AdapterErrorCode, BrokerAdapterError, redact_secrets


class AlpacaPaperTransport:
    """独立 REST 客户端（仅 Paper base URL）。"""

    def __init__(self, credentials: Mapping[str, str] | None = None) -> None:
        creds = dict(credentials or load_alpaca_paper_credentials())
        if not creds.get("api_key") or not creds.get("api_secret"):
            raise BrokerAdapterError(
                "ALPACA_PAPER_API_KEY/SECRET required",
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
        url = f"{self.base_url}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method=method.upper())
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
                redact_secrets(f"alpaca HTTP {exc.code}: {detail}"),
                code=AdapterErrorCode.REJECTED
                if exc.code in (400, 403, 422)
                else AdapterErrorCode.NETWORK_UNKNOWN,
            ) from exc
        except URLError as exc:
            raise BrokerAdapterError(
                redact_secrets(f"alpaca network: {exc}"),
                code=AdapterErrorCode.NETWORK_UNKNOWN,
            ) from exc

    def submit_order(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/v2/orders", body=dict(payload))

    def cancel_order(self, broker_order_id: str) -> dict[str, Any]:
        return self.request("DELETE", f"/v2/orders/{broker_order_id}")

    def replace_order(
        self, broker_order_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self.request(
            "PATCH", f"/v2/orders/{broker_order_id}", body=dict(payload)
        )

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any]:
        return self.request(
            "GET", f"/v2/orders:by_client_order_id?client_order_id={client_order_id}"
        )

    def get_order(self, broker_order_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v2/orders/{broker_order_id}")

    def list_open_orders(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/v2/orders?status=open&limit=100")
        return list(data) if isinstance(data, list) else []

    def get_account(self) -> dict[str, Any]:
        return self.request("GET", "/v2/account")

    def get_positions(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/v2/positions")
        return list(data) if isinstance(data, list) else []
