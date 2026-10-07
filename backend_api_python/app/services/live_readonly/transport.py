"""Phase 7A：Alpaca Live GET-only transport；测试用 FakeTransport。"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError, redact_secrets

from .credentials import load_alpaca_live_credentials

# 写路径硬禁（AST/测试也会扫描）
_FORBIDDEN_ORDER_WRITE_PATHS = frozenset({"/v2/orders"})


class AlpacaLiveReadonlyTransport:
    """Live REST：仅 GET；永不 POST /v2/orders。"""

    def __init__(self, credentials: Mapping[str, str] | None = None) -> None:
        creds = dict(credentials or load_alpaca_live_credentials())
        if not creds.get("api_key") or not creds.get("api_secret"):
            raise BrokerAdapterError(
                "ALPACA_LIVE_API_KEY/SECRET required",
                code=AdapterErrorCode.AUTH_FAILED,
            )
        self.base_url = str(creds["base_url"]).rstrip("/")
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
                f"LIVE_READONLY: HTTP {m} forbidden",
                code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
            )
        p = path.split("?", 1)[0].rstrip("/")
        if p in _FORBIDDEN_ORDER_WRITE_PATHS and m != "GET":
            raise BrokerAdapterError(
                "LIVE_READONLY: POST /v2/orders forbidden",
                code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
            )

        url = f"{self.base_url}{path}"
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

    def get_account(self) -> dict[str, Any]:
        return self.request("GET", "/v2/account")

    def get_positions(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/v2/positions")
        return list(data) if isinstance(data, list) else []

    def list_open_orders(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/v2/orders?status=open&limit=100")
        return list(data) if isinstance(data, list) else []

    def get_order(self, broker_order_id: str) -> dict[str, Any]:
        return self.request("GET", f"/v2/orders/{broker_order_id}")

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/v2/orders:by_client_order_id?client_order_id={client_order_id}",
        )

    def list_activities(
        self, *, activity_type: str = "FILL", page_size: int = 100
    ) -> list[dict[str, Any]]:
        """成交/活动只读查询（Alpaca account activities）。"""
        q = f"/v2/account/activities?activity_types={activity_type}&page_size={page_size}"
        data = self.request("GET", q)
        return list(data) if isinstance(data, list) else []


class FakeLiveReadonlyTransport:
    """测试用内存 transport；不触网。"""

    def __init__(
        self,
        *,
        account: Mapping[str, Any] | None = None,
        positions: list[Mapping[str, Any]] | None = None,
        orders: list[Mapping[str, Any]] | None = None,
        activities: list[Mapping[str, Any]] | None = None,
    ) -> None:
        self._account = dict(
            account
            or {
                "id": "fake-live-acct",
                "currency": "USD",
                "cash": "10000",
                "buying_power": "10000",
                "equity": "10000",
                "status": "ACTIVE",
            }
        )
        self._positions = [dict(p) for p in (positions or [])]
        self._orders = [dict(o) for o in (orders or [])]
        self._activities = [dict(a) for a in (activities or [])]
        self.base_url = "https://api.alpaca.markets"

    def get_account(self) -> dict[str, Any]:
        return dict(self._account)

    def get_positions(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self._positions]

    def list_open_orders(self) -> list[dict[str, Any]]:
        return [dict(o) for o in self._orders]

    def get_order(self, broker_order_id: str) -> dict[str, Any]:
        for o in self._orders:
            if str(o.get("id")) == broker_order_id:
                return dict(o)
        return {"id": broker_order_id, "status": "unknown"}

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any]:
        for o in self._orders:
            if str(o.get("client_order_id")) == client_order_id:
                return dict(o)
        return {"client_order_id": client_order_id, "status": "unknown"}

    def list_activities(
        self, *, activity_type: str = "FILL", page_size: int = 100
    ) -> list[dict[str, Any]]:
        _ = activity_type, page_size
        return [dict(a) for a in self._activities]

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Fake 层同样拒绝写 HTTP。"""
        if method.upper() != "GET":
            raise BrokerAdapterError(
                f"LIVE_READONLY: HTTP {method} forbidden",
                code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
            )
        if "POST" in method.upper() or path.startswith("/v2/orders") and method.upper() == "POST":
            raise BrokerAdapterError(
                "LIVE_READONLY: POST /v2/orders forbidden",
                code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
            )
        if path.startswith("/v2/account"):
            return self.get_account()
        if path.startswith("/v2/positions"):
            return self.get_positions()
        if path.startswith("/v2/orders"):
            return self.list_open_orders()
        if path.startswith("/v2/account/activities"):
            return self.list_activities()
        return {}
