"""Adapter 错误码与异常（映射到 ExecutionReport，不泄漏密钥）。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class AdapterErrorCode(str, Enum):
    """标准化错误码。"""

    UNSUPPORTED_ORDER_TYPE = "UNSUPPORTED_ORDER_TYPE"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    NETWORK_UNKNOWN = "NETWORK_UNKNOWN"
    REJECTED = "REJECTED"
    LIVE_FORBIDDEN = "LIVE_FORBIDDEN"
    LIVE_READONLY_FORBIDDEN = "LIVE_READONLY_FORBIDDEN"
    NOT_CONNECTED = "NOT_CONNECTED"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_FAILED = "AUTH_FAILED"
    INTERNAL = "INTERNAL"


class BrokerAdapterError(RuntimeError):
    """Broker Adapter 编排/能力错误。"""

    def __init__(
        self,
        message: str,
        *,
        code: AdapterErrorCode = AdapterErrorCode.INTERNAL,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def redact_secrets(text: str) -> str:
    """日志/异常脱敏：掩码疑似密钥片段。"""
    import re

    out = str(text or "")
    out = re.sub(
        r"(?i)(api[_-]?key|secret|token|password|authorization)\s*[:=]\s*\S+",
        r"\1=***",
        out,
    )
    out = re.sub(r"\b[A-Za-z0-9_\-]{32,}\b", "***", out)
    return out
