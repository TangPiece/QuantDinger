"""从百度网盘补 Level2 明细 Parquet。

逻辑键是 ``{前缀}/{YYYYMMDD}/{代码}/{类型}.parquet``，网盘物理路径在日期前
插入年/年月。凭证和 level2 入库使用同一组环境变量。

同一时刻只发一个百度 HTTP。连接超时连续达到阈值时休眠后再继续。
令牌失效并刷新成功后回写 ``.env``，避免下次启动仍用过期 token。
瞬态网络错误会指数退避重试；真缺文件返回 None。同目录 fsid 只列一次。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from .prep import is_equity

_PAN_FILE_API = "https://pan.baidu.com/rest/2.0/xpan/file"
_PAN_META_API = "https://pan.baidu.com/rest/2.0/xpan/multimedia"
_TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token"
_UA = "pan.baidu.com"
# (connect, read)：百度链路经常慢，连接给 30 秒，读文件给 3 分钟。
_TIMEOUT = (30, 180)
_RETRY_ATTEMPTS = 3
_RETRY_BASE_SEC = 1.0
# 连续连不上就停一会儿，避免在不通的链路上空打。
_BREAKER_THRESHOLD = 5
_BREAKER_SLEEP_SEC = 60.0
_log = logging.getLogger(__name__)
_token: str | None = None
# 多路下载同时发现令牌过期时，只刷新一次。
_token_lock = threading.Lock()
# 同一股票目录只列一次，避免三类明细各打一次 list。
_dir_cache_lock = threading.Lock()
_dir_fsid_cache: dict[str, dict[str, int]] = {}
# 全进程串行，避免多线程同时打 pan.baidu.com。
_http_lock = threading.Lock()
_consecutive_connect_fails = 0


def download_book_bytes(date: str, code: str, ftype: str) -> bytes | None:
    """下载一天一只股票的一类明细。

    没有凭证或网盘没有该文件时返回 None。
    连接超时等瞬态错误重试耗尽后抛出，不再伪装成缺文件。
    """
    if not _configured():
        return None
    path = remote_path(date, code, ftype)
    try:
        fsid = _fsid(path)
        if fsid is None:
            return None
        return _download(path, fsid)
    except FileNotFoundError:
        return None
    except Exception as exc:
        if _is_transient(exc):
            # 重试已在下层做过；这里只记一行，不刷整段 traceback。
            _log.warning("百度明细下载失败 %s %s %s: %s", date, code, ftype, exc)
            raise
        _log.warning("百度明细下载失败 %s %s %s: %s", date, code, ftype, exc)
        raise


def list_equity_codes(date: str) -> list[str]:
    """列出网盘上这一天的 A 股代码目录。列不出时返回空列表。"""
    if not _configured():
        return []
    folder = _date_dir(date)
    try:
        entries = _list_dir(folder)
    except Exception as exc:
        _log.warning("百度明细列目录失败 %s: %s", date, exc)
        return []
    codes = []
    for item in entries:
        if not item.get("isdir"):
            continue
        name = str(item.get("server_filename") or "")
        if is_equity(name):
            codes.append(name)
    return sorted(set(codes))


def clear_dir_cache() -> None:
    """测试或强制刷新时清空目录 fsid 缓存。"""
    with _dir_cache_lock:
        _dir_fsid_cache.clear()


def reset_http_state() -> None:
    """测试用：清掉连续超时计数，避免用例互相影响。"""
    global _consecutive_connect_fails
    _consecutive_connect_fails = 0


def remote_path(date: str, code: str, ftype: str) -> str:
    """网盘绝对路径，日期按年/年月分层。"""
    prefix = os.getenv("BAIDU_REMOTE_PREFIX", "l2").strip() or "l2"
    day = str(date).strip()
    nested = f"{prefix}/{day[:4]}/{day[:6]}/{day}/{code}/{ftype}.parquet"
    return f"{_apps_root()}/{nested}"


def _date_dir(date: str) -> str:
    prefix = os.getenv("BAIDU_REMOTE_PREFIX", "l2").strip() or "l2"
    day = str(date).strip()
    return f"{_apps_root()}/{prefix}/{day[:4]}/{day[:6]}/{day}"


def _apps_root() -> str:
    name = os.getenv("BAIDU_APP_NAME", "level2").strip() or "level2"
    return f"/apps/{name}"


def _configured() -> bool:
    return bool(os.getenv("BAIDU_ACCESS_TOKEN", "").strip() or _token)


def _access_token() -> str:
    return _token or os.getenv("BAIDU_ACCESS_TOKEN", "").strip()


def _env_path() -> Path:
    """后端根目录的 ``.env``。测试可替换，避免改到本机凭证。"""
    return Path(__file__).resolve().parents[3] / ".env"


def _persist_tokens(updates: dict[str, str]) -> None:
    """把刷新后的 token 写回 .env，并同步到当前进程环境。"""
    path = _env_path()
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        matched = False
        for key, val in updates.items():
            if line.startswith(f"{key}="):
                out.append(f"{key}={val}")
                seen.add(key)
                matched = True
                break
        if not matched:
            out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(out) + "\n")
    for key, val in updates.items():
        os.environ[key] = val


def _refresh_token(expected: str | None = None) -> str:
    """令牌失效时刷新，并回写 ``.env``。

    ``expected`` 是这次请求用过的令牌。锁里如果已经被别的线程换成新令牌，直接复用，不再打第二次刷新。
    """
    global _token
    with _token_lock:
        if _token and expected is not None and _token != expected:
            return _token
        params = {
            "grant_type": "refresh_token",
            "refresh_token": os.getenv("BAIDU_REFRESH_TOKEN", "").strip(),
            "client_id": os.getenv("BAIDU_APP_KEY", "").strip(),
            "client_secret": os.getenv("BAIDU_SECRET_KEY", "").strip(),
        }
        if not params["refresh_token"] or not params["client_id"]:
            return _access_token()
        resp = _locked_get(_TOKEN_URL, params=params, label="token refresh")
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"Baidu token refresh failed: {data}")
        updates = {"BAIDU_ACCESS_TOKEN": str(data["access_token"])}
        if data.get("refresh_token"):
            updates["BAIDU_REFRESH_TOKEN"] = str(data["refresh_token"])
        _token = updates["BAIDU_ACCESS_TOKEN"]
        _persist_tokens(updates)
        return _token


def _is_transient(exc: BaseException) -> bool:
    """连接超时、断连、HTTP 5xx 视为可重试。"""
    if isinstance(
        exc,
        (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ),
    ):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return bool(status and int(status) >= 500)
    return False


def _with_retry(fn, *, label: str):
    """对瞬态错误做指数退避；非瞬态或耗尽后原样抛出。"""
    last: BaseException | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if not _is_transient(exc) or attempt + 1 >= _RETRY_ATTEMPTS:
                raise
            delay = _RETRY_BASE_SEC * (2 ** attempt)
            _log.warning("%s 瞬态失败，%.1fs 后重试 (%s/%s): %s", label, delay, attempt + 1, _RETRY_ATTEMPTS, exc)
            time.sleep(delay)
    assert last is not None
    raise last


def _is_connect_failure(exc: BaseException) -> bool:
    """连不上对端才计入熔断。读超时和 5xx 仍只走普通重试。"""
    return isinstance(
        exc,
        (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError),
    )


def _note_connect_ok() -> None:
    global _consecutive_connect_fails
    _consecutive_connect_fails = 0


def _note_connect_fail() -> None:
    """连续连不上达到阈值后休眠。调用方已持有 HTTP 锁。"""
    global _consecutive_connect_fails
    _consecutive_connect_fails += 1
    if _consecutive_connect_fails < _BREAKER_THRESHOLD:
        return
    _consecutive_connect_fails = 0
    _log.warning("连续连接失败 %s 次，熔断休眠 %.0fs", _BREAKER_THRESHOLD, _BREAKER_SLEEP_SEC)
    time.sleep(_BREAKER_SLEEP_SEC)


def _locked_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    label: str,
) -> requests.Response:
    """串行 GET。成功清计数；连接失败累计到熔断。"""
    del label
    with _http_lock:
        try:
            resp = requests.get(url, params=params, headers=headers, allow_redirects=True, timeout=_TIMEOUT)
            if resp.status_code >= 400:
                resp.raise_for_status()
            _note_connect_ok()
            return resp
        except Exception as exc:
            if _is_connect_failure(exc):
                _note_connect_fail()
            raise


def _http_get(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, label: str) -> requests.Response:
    """带瞬态重试的 GET。底层请求全局串行。"""

    def once() -> requests.Response:
        return _locked_get(url, params=params, headers=headers, label=label)

    return _with_retry(once, label=label)


def _api_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    used = _access_token()
    query = {**params, "access_token": used}
    resp = _http_get(url, params=query, label=f"api {params.get('method') or url}")
    data = resp.json()
    if data.get("errno") in (31045, -6) and os.getenv("BAIDU_REFRESH_TOKEN", "").strip():
        _log.warning("百度 API errno=%s，刷新令牌后重试", data.get("errno"))
        query["access_token"] = _refresh_token(expected=used)
        resp = _http_get(url, params=query, label=f"api-refresh {params.get('method') or url}")
        data = resp.json()
    errno = data.get("errno", 0)
    if errno != 0:
        _log.warning("百度 API errno=%s method=%s", errno, params.get("method"))
        raise RuntimeError(f"Baidu API errno={errno}: {data}")
    return data


def _list_dir(abs_dir: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    start = 0
    while True:
        try:
            data = _api_get(
                _PAN_FILE_API,
                {
                    "method": "list",
                    "dir": abs_dir,
                    "start": start,
                    "limit": 1000,
                    "folder": "0",
                },
            )
        except RuntimeError as exc:
            # 目录不存在时网盘返回 errno=-9，按没有这一天处理。
            if "errno=-9" in str(exc):
                return []
            raise
        batch = data.get("list") or []
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 1000:
            break
        start += 1000
    return items


def _dir_name_map(parent: str) -> dict[str, int]:
    """列出父目录并缓存 filename -> fs_id。"""
    key = parent or "/"
    with _dir_cache_lock:
        cached = _dir_fsid_cache.get(key)
        if cached is not None:
            return cached
    entries = _list_dir(key)
    mapping: dict[str, int] = {}
    for item in entries:
        if item.get("isdir"):
            continue
        name = str(item.get("server_filename") or "")
        if not name or "fs_id" not in item:
            continue
        mapping[name] = int(item["fs_id"])
    with _dir_cache_lock:
        _dir_fsid_cache[key] = mapping
    return mapping


def _fsid(abs_path: str) -> int | None:
    parent, _, name = abs_path.rpartition("/")
    return _dir_name_map(parent or "/").get(name)


def _download(abs_path: str, fsid: int) -> bytes:
    data = _api_get(
        _PAN_META_API,
        {"method": "filemetas", "fsids": f"[{fsid}]", "dlink": "1"},
    )
    metas = data.get("list") or data.get("info") or []
    if not metas or not metas[0].get("dlink"):
        raise FileNotFoundError(abs_path)
    dlink = str(metas[0]["dlink"]).replace("\\u0026", "&")
    token = _access_token()
    url = dlink if "access_token=" in dlink else f"{dlink}&{urlencode({'access_token': token})}"
    resp = _http_get(url, headers={"User-Agent": _UA}, label=f"download {abs_path}")
    resp.raise_for_status()
    return resp.content
