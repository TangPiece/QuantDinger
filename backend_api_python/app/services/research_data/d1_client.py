"""经 qd-research-d1 Worker 访问 D1 qd_research。

使用 D1_RESEARCH_WORKER_URL / D1_RESEARCH_WORKER_TOKEN，
与 Level2 的 D1_WORKER_* 完全隔离。
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from . import config

_log = logging.getLogger(__name__)

MAX_BATCH_STATEMENTS = 200
_TIMEOUT = 120
_POST_RETRIES = 4
_POST_BACKOFF_SEC = (1.0, 2.0, 4.0, 8.0)


class D1ResearchError(RuntimeError):
    """研究 D1 Worker 失败。"""


def configured() -> bool:
    return config.d1_research_configured()


def query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """执行单条 SQL，返回结果行。"""
    payload = _post("/v1/query", {"sql": sql, "params": list(params or [])})
    return _rows_from_results(payload.get("results") or [])


def batch(statements: list[dict[str, Any]]) -> list[Any]:
    if not statements:
        return []
    if len(statements) > MAX_BATCH_STATEMENTS:
        raise D1ResearchError(f"batch 超过上限 {MAX_BATCH_STATEMENTS}")
    payload = _post("/v1/batch", {"statements": statements})
    return list(payload.get("results") or [])


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    if not configured():
        raise D1ResearchError("D1 Research Worker 未配置")
    url = config.d1_research_worker_url().rstrip("/") + path
    headers = {
        "Authorization": f"Bearer {config.d1_research_worker_token()}",
        "Content-Type": "application/json",
    }
    last_exc: Exception | None = None
    for attempt in range(_POST_RETRIES):
        try:
            response = requests.post(url, json=body, headers=headers, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt + 1 >= _POST_RETRIES:
                break
            delay = _POST_BACKOFF_SEC[min(attempt, len(_POST_BACKOFF_SEC) - 1)]
            _log.warning(
                "D1 Research %s 瞬态失败，%.1fs 后重试 (%s/%s): %s",
                path, delay, attempt + 1, _POST_RETRIES, exc,
            )
            time.sleep(delay)
            continue
        try:
            payload = response.json()
        except ValueError as exc:
            raise D1ResearchError(f"响应非 JSON HTTP {response.status_code}") from exc
        if response.status_code >= 400 or not payload.get("ok"):
            error = payload.get("error") or f"HTTP {response.status_code}"
            if response.status_code >= 500 and attempt + 1 < _POST_RETRIES:
                delay = _POST_BACKOFF_SEC[min(attempt, len(_POST_BACKOFF_SEC) - 1)]
                time.sleep(delay)
                continue
            raise D1ResearchError(str(error))
        return payload
    raise D1ResearchError(f"D1 Research 请求失败: {last_exc}") from last_exc


def _rows_from_results(results: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        part = item.get("results")
        if isinstance(part, list):
            for row in part:
                if isinstance(row, dict):
                    rows.append(row)
    return rows
