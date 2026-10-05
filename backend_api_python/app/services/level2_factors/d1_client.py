"""经 Cloudflare Worker 代理访问 D1。

后端只配置 ``D1_WORKER_URL`` 与 ``D1_WORKER_TOKEN``，不直连 Cloudflare D1 REST。
凭证未配齐时 ``configured()`` 为 False，调用方应跳过远端读写。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

_log = logging.getLogger(__name__)

# 与 Worker 侧 MAX_BATCH_STATEMENTS 对齐。
MAX_BATCH_STATEMENTS = 200
_TIMEOUT = 120
# 全量日宽表写入时偶发 ConnectTimeout，短退避重试避免半日残留。
_POST_RETRIES = 4
_POST_BACKOFF_SEC = (1.0, 2.0, 4.0, 8.0)


class D1WorkerError(RuntimeError):
    """Worker 返回非成功或网络失败。"""


def configured() -> bool:
    """Worker URL 与 Token 都非空才视为可用。"""
    return bool(_worker_url() and _worker_token())


def query(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """执行单条 SQL，返回结果集行（写语句通常为空列表）。"""
    payload = _post("/v1/query", {"sql": sql, "params": list(params or [])})
    return _rows_from_results(payload.get("results") or [])


def batch(statements: list[dict[str, Any]]) -> list[Any]:
    """批量执行。每项为 ``{"sql": str, "params": list}``。"""
    if not statements:
        return []
    # 超过 Worker 上限时由调用方切块；这里再兜一层。
    if len(statements) > MAX_BATCH_STATEMENTS:
        raise D1WorkerError(f"batch 超过上限 {MAX_BATCH_STATEMENTS}")
    payload = _post("/v1/batch", {"statements": statements})
    return list(payload.get("results") or [])


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST Worker；网络类错误按指数退避重试。"""
    if not configured():
        raise D1WorkerError("D1 Worker 未配置")
    url = _worker_url().rstrip("/") + path
    headers = {
        "Authorization": f"Bearer {_worker_token()}",
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
            _log.warning("D1 Worker %s 瞬态失败，%.1fs 后重试 (%s/%s): %s", path, delay, attempt + 1, _POST_RETRIES, exc)
            time.sleep(delay)
            continue
        try:
            payload = response.json()
        except ValueError as exc:
            raise D1WorkerError(f"D1 Worker 响应非 JSON HTTP {response.status_code}") from exc
        if response.status_code >= 400 or not payload.get("ok"):
            error = payload.get("error") or f"HTTP {response.status_code}"
            # 5xx 可重试；4xx / 业务 ok=false 直接失败。
            if response.status_code >= 500 and attempt + 1 < _POST_RETRIES:
                delay = _POST_BACKOFF_SEC[min(attempt, len(_POST_BACKOFF_SEC) - 1)]
                _log.warning("D1 Worker %s HTTP %s，%.1fs 后重试 (%s/%s)", path, response.status_code, delay, attempt + 1, _POST_RETRIES)
                time.sleep(delay)
                continue
            raise D1WorkerError(str(error))
        return payload
    raise D1WorkerError(f"D1 Worker 请求失败: {last_exc}") from last_exc


def _rows_from_results(results: list[Any]) -> list[dict[str, Any]]:
    """从 Worker 包装的 D1 结果里抽出行字典。"""
    rows: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        # D1 .all() 形状：{"results": [...], "success": true, "meta": {...}}
        part = item.get("results")
        if isinstance(part, list):
            for row in part:
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def _worker_url() -> str:
    return os.getenv("D1_WORKER_URL", "").strip()


def _worker_token() -> str:
    return os.getenv("D1_WORKER_TOKEN", "").strip()
