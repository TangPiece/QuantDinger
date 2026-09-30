"""从百度网盘补 Level2 明细 Parquet。

逻辑键是 ``{前缀}/{YYYYMMDD}/{代码}/{类型}.parquet``，网盘物理路径在日期前
插入年/年月。凭证和 level2 入库使用同一组环境变量。这里只下载，不改 ``.env``。
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any
from urllib.parse import urlencode

import requests

from .prep import is_equity

_PAN_FILE_API = "https://pan.baidu.com/rest/2.0/xpan/file"
_PAN_META_API = "https://pan.baidu.com/rest/2.0/xpan/multimedia"
_TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token"
_UA = "pan.baidu.com"
_log = logging.getLogger(__name__)
_token: str | None = None
# 多路下载同时发现令牌过期时，只刷新一次。
_token_lock = threading.Lock()


def download_book_bytes(date: str, code: str, ftype: str) -> bytes | None:
    """下载一天一只股票的一类明细。没有凭证或网盘没有该文件时返回 None。"""
    if not _configured():
        return None
    path = remote_path(date, code, ftype)
    try:
        fsid = _fsid(path)
        if fsid is None:
            return None
        return _download(path, fsid)
    except Exception:
        _log.warning("百度明细下载失败 %s %s %s", date, code, ftype, exc_info=True)
        return None


def list_equity_codes(date: str) -> list[str]:
    """列出网盘上这一天的 A 股代码目录。列不出时返回空列表。"""
    if not _configured():
        return []
    folder = _date_dir(date)
    try:
        entries = _list_dir(folder)
    except Exception:
        _log.warning("百度明细列目录失败 %s", date, exc_info=True)
        return []
    codes = []
    for item in entries:
        if not item.get("isdir"):
            continue
        name = str(item.get("server_filename") or "")
        if is_equity(name):
            codes.append(name)
    return sorted(set(codes))


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


def _refresh_token(expected: str | None = None) -> str:
    """令牌失效时在本进程内刷新。不回写环境文件。

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
        resp = requests.get(_TOKEN_URL, params=params, timeout=30)
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"Baidu token refresh failed: {data}")
        _token = str(data["access_token"])
        return _token


def _api_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    used = _access_token()
    query = {**params, "access_token": used}
    resp = requests.get(url, params=query, timeout=60)
    data = resp.json()
    if data.get("errno") in (31045, -6) and os.getenv("BAIDU_REFRESH_TOKEN", "").strip():
        query["access_token"] = _refresh_token(expected=used)
        resp = requests.get(url, params=query, timeout=60)
        data = resp.json()
    errno = data.get("errno", 0)
    if errno != 0:
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


def _fsid(abs_path: str) -> int | None:
    parent, _, name = abs_path.rpartition("/")
    for item in _list_dir(parent or "/"):
        if item.get("server_filename") == name and not item.get("isdir"):
            return int(item["fs_id"])
    return None


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
    resp = requests.get(url, headers={"User-Agent": _UA}, allow_redirects=True, timeout=300)
    resp.raise_for_status()
    return resp.content
