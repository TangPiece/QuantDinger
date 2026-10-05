"""Baidu Pan open platform API client: OAuth, upload, download, list."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from . import config

# 4MB PCS block size
_BLOCK_SIZE = 4 * 1024 * 1024
_DLINK_SKEW_SEC = 300
_TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token"
_PAN_FILE_API = "https://pan.baidu.com/rest/2.0/xpan/file"
_PAN_META_API = "https://pan.baidu.com/rest/2.0/xpan/multimedia"
_PCS_UPLOAD = "https://d.pcs.baidu.com/rest/2.0/pcs/superfile2"
_UA = "pan.baidu.com"

_token_lock = threading.Lock()
_access_token: str | None = None
_dlink_cache: dict[str, tuple[str, float]] = {}


def is_configured() -> bool:
    return bool(config.BAIDU_APP_KEY and config.BAIDU_SECRET_KEY and _effective_token())


def _effective_token() -> str:
    return _access_token or config.BAIDU_ACCESS_TOKEN


def _env_path() -> Path:
    return config.ROOT / ".env"


def _persist_env(updates: dict[str, str]) -> None:
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
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    global _access_token
    for key, val in updates.items():
        if key == "BAIDU_ACCESS_TOKEN":
            _access_token = val
        setattr(config, key, val)


def ensure_token() -> str:
    tok = _effective_token()
    if not tok:
        raise RuntimeError("BAIDU_ACCESS_TOKEN missing; run scripts/baidu_oauth.py")
    return tok


def _refresh_access_token() -> str:
    params = {
        "grant_type": "refresh_token",
        "refresh_token": config.BAIDU_REFRESH_TOKEN,
        "client_id": config.BAIDU_APP_KEY,
        "client_secret": config.BAIDU_SECRET_KEY,
    }
    resp = requests.get(_TOKEN_URL, params=params, timeout=30)
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Baidu token refresh failed: {data}")
    updates = {"BAIDU_ACCESS_TOKEN": data["access_token"]}
    if data.get("refresh_token"):
        updates["BAIDU_REFRESH_TOKEN"] = data["refresh_token"]
    _persist_env(updates)
    return data["access_token"]


def exchange_code(code: str) -> dict[str, Any]:
    params = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "client_id": config.BAIDU_APP_KEY,
        "client_secret": config.BAIDU_SECRET_KEY,
        "redirect_uri": config.BAIDU_REDIRECT_URI,
    }
    resp = requests.get(_TOKEN_URL, params=params, timeout=30)
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Baidu OAuth failed: {data}")
    updates = {"BAIDU_ACCESS_TOKEN": data["access_token"]}
    if data.get("refresh_token"):
        updates["BAIDU_REFRESH_TOKEN"] = data["refresh_token"]
    _persist_env(updates)
    return data


def build_authorize_url() -> str:
    params = {
        "response_type": "code",
        "client_id": config.BAIDU_APP_KEY,
        "redirect_uri": config.BAIDU_REDIRECT_URI,
        "scope": "basic,netdisk",
        "display": "popup",
    }
    return f"https://openapi.baidu.com/oauth/2.0/authorize?{urlencode(params)}"


def _api_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    token = ensure_token()
    params = {**params, "access_token": token}
    resp = requests.get(url, params=params, timeout=60)
    data = resp.json()
    errno = data.get("errno", 0)
    if errno in (31045, -6) and config.BAIDU_REFRESH_TOKEN:
        with _token_lock:
            _refresh_access_token()
        params["access_token"] = _effective_token()
        resp = requests.get(url, params=params, timeout=60)
        data = resp.json()
        errno = data.get("errno", 0)
    if errno != 0:
        raise RuntimeError(f"Baidu API errno={errno}: {data}")
    return data


def _api_post(url: str, params: dict[str, Any], data: dict[str, Any] | None = None) -> dict[str, Any]:
    token = ensure_token()
    params = {**params, "access_token": token}
    resp = requests.post(url, params=params, data=data or {}, timeout=120)
    body = resp.json()
    errno = body.get("errno", 0)
    if errno in (31045, -6) and config.BAIDU_REFRESH_TOKEN:
        with _token_lock:
            _refresh_access_token()
        params["access_token"] = _effective_token()
        resp = requests.post(url, params=params, data=data or {}, timeout=120)
        body = resp.json()
        errno = body.get("errno", 0)
    if errno != 0:
        raise RuntimeError(f"Baidu API errno={errno}: {body}")
    return body


def _md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _block_md5_list(data: bytes) -> list[str]:
    if not data:
        return [_md5_hex(b"")]
    blocks: list[str] = []
    for i in range(0, len(data), _BLOCK_SIZE):
        blocks.append(_md5_hex(data[i : i + _BLOCK_SIZE]))
    return blocks


def upload_bytes(remote_path: str, data: bytes) -> str:
    path = remote_path if remote_path.startswith("/") else f"/{remote_path}"
    if not path.startswith(config.baidu_apps_root()):
        raise ValueError(f"Baidu path must be under {config.baidu_apps_root()}: {path}")

    block_list = _block_md5_list(data)
    pre = _api_post(
        _PAN_FILE_API,
        {"method": "precreate"},
        {
            "path": path,
            "size": str(len(data)),
            "isdir": "0",
            "autoinit": "1",
            "rtype": "3",
            "block_list": json.dumps(block_list),
        },
    )
    uploadid = pre["uploadid"]

    for seq, _md5 in enumerate(block_list):
        start = seq * _BLOCK_SIZE
        chunk = data[start : start + _BLOCK_SIZE]
        params = {
            "method": "upload",
            "type": "tmpfile",
            "path": path,
            "uploadid": uploadid,
            "partseq": str(seq),
        }
        token = ensure_token()
        resp = requests.post(
            _PCS_UPLOAD,
            params={**params, "access_token": token},
            files={"file": ("chunk", chunk)},
            timeout=300,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Baidu chunk upload failed part={seq}: {resp.text[:500]}")

    _api_post(
        _PAN_FILE_API,
        {"method": "create"},
        {
            "path": path,
            "size": str(len(data)),
            "isdir": "0",
            "rtype": "3",
            "uploadid": uploadid,
            "block_list": json.dumps(block_list),
        },
    )
    file_md5 = _md5_hex(data)
    _dlink_cache.pop(path, None)
    return file_md5


def _list_dir(abs_dir: str) -> list[dict[str, Any]]:
    abs_dir = abs_dir if abs_dir.startswith("/") else f"/{abs_dir}"
    items: list[dict[str, Any]] = []
    start = 0
    while True:
        data = _api_get(
            _PAN_FILE_API,
            {
                "method": "list",
                "dir": abs_dir,
                "order": "time",
                "desc": "0",
                "start": start,
                "limit": 1000,
                "web": "web",
                "folder": "0",
            },
        )
        batch = data.get("list") or []
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 1000:
            break
        start += 1000
    return items


def _get_fsid_by_path(abs_path: str) -> int | None:
    abs_path = abs_path if abs_path.startswith("/") else f"/{abs_path}"
    parent = str(Path(abs_path).parent).replace("\\", "/") or "/"
    name = Path(abs_path).name
    try:
        for item in _list_dir(parent):
            if item.get("server_filename") == name and not item.get("isdir"):
                return int(item["fs_id"])
    except RuntimeError as exc:
        if "errno=-9" in str(exc) or "errno=31066" in str(exc):
            return None
        raise
    return None


def exists(remote_path: str) -> bool:
    return _get_fsid_by_path(remote_path) is not None


def _filemetas_dlink(fsid: int) -> str:
    data = _api_get(
        _PAN_META_API,
        {
            "method": "filemetas",
            "fsids": json.dumps([fsid]),
            "dlink": "1",
        },
    )
    metas = data.get("list") or data.get("info") or []
    if not metas:
        raise FileNotFoundError(f"Baidu filemetas empty fsid={fsid}")
    dlink = metas[0].get("dlink", "")
    if not dlink:
        raise RuntimeError(f"Baidu dlink missing: {metas[0]}")
    return dlink.replace("\\u0026", "&")


def _get_dlink(abs_path: str) -> str:
    now = time.time()
    cached = _dlink_cache.get(abs_path)
    if cached and cached[1] > now:
        return cached[0]
    fsid = _get_fsid_by_path(abs_path)
    if fsid is None:
        raise FileNotFoundError(abs_path)
    dlink = _filemetas_dlink(fsid)
    _dlink_cache[abs_path] = (dlink, now + 8 * 3600 - _DLINK_SKEW_SEC)
    return dlink


def download_bytes(remote_path: str) -> bytes:
    abs_path = remote_path if remote_path.startswith("/") else f"/{remote_path}"
    dlink = _get_dlink(abs_path)
    token = ensure_token()
    url = dlink if "access_token=" in dlink else f"{dlink}&access_token={token}"
    resp = requests.get(
        url,
        headers={"User-Agent": _UA},
        allow_redirects=True,
        timeout=300,
    )
    if resp.status_code == 403:
        _dlink_cache.pop(abs_path, None)
        dlink = _get_dlink(abs_path)
        url = dlink if "access_token=" in dlink else f"{dlink}&access_token={token}"
        resp = requests.get(url, headers={"User-Agent": _UA}, allow_redirects=True, timeout=300)
    resp.raise_for_status()
    return resp.content


def _logical_key_from_baidu_path(abs_path: str) -> str | None:
    """绝对路径 → 逻辑键（去掉年/年月物理层级）。"""
    root = config.baidu_apps_root().rstrip("/") + "/"
    if not abs_path.startswith(root):
        return None
    rel = abs_path[len(root) :]
    return config.baidu_rel_to_logical_key(rel)


def list_keys(prefix: str) -> list[str]:
    """按逻辑前缀列举；物理目录可能含年/年月层，返回仍为逻辑键。"""
    prefix = prefix.strip("/")
    # 逻辑 l2/20260506/ → 物理 l2/2026/202605/20260506/
    physical = config.logical_key_to_baidu_rel(prefix)
    base = f"{config.baidu_apps_root()}/{physical}"
    keys: list[str] = []

    def walk(abs_dir: str) -> None:
        try:
            entries = _list_dir(abs_dir)
        except RuntimeError as exc:
            if "errno=-9" in str(exc):
                return
            raise
        for ent in entries:
            path = ent.get("path") or f"{abs_dir.rstrip('/')}/{ent.get('server_filename', '')}"
            if ent.get("isdir"):
                walk(path)
            elif path.endswith(".parquet"):
                lk = _logical_key_from_baidu_path(path)
                if lk and lk.startswith(prefix):
                    keys.append(lk)

    walk(base)
    return sorted(keys)


def configure_pool(min_connections: int) -> None:
    _ = min_connections
