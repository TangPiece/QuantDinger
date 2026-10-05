"""百度明细下载：瞬态重试、目录 fsid 缓存、串行与令牌回写。"""
from __future__ import annotations

import threading
from unittest.mock import Mock

import pytest
import requests


@pytest.fixture(autouse=True)
def _baidu_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BAIDU_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("BAIDU_APP_NAME", "level2")
    monkeypatch.setenv("BAIDU_REMOTE_PREFIX", "l2")
    from app.services.level2_factors import baidu_books

    baidu_books.clear_dir_cache()
    baidu_books.reset_http_state()
    baidu_books._token = None
    monkeypatch.setattr(baidu_books, "_RETRY_BASE_SEC", 0)
    yield
    baidu_books.clear_dir_cache()
    baidu_books.reset_http_state()
    baidu_books._token = None


def test_download_retries_transient_then_succeeds(monkeypatch: pytest.MonkeyPatch):
    """前两次连接超时，第三次成功拿到内容。"""
    from app.services.level2_factors import baidu_books

    list_payload = {
        "errno": 0,
        "list": [{"server_filename": "行情.parquet", "isdir": 0, "fs_id": 11}],
    }
    meta_payload = {"errno": 0, "list": [{"dlink": "https://d.pcs.baidu.com/file?x=1"}]}
    dl_attempts = {"n": 0}

    def fake_get(url, params=None, headers=None, allow_redirects=True, timeout=None):
        if "pan.baidu.com" in str(url):
            method = (params or {}).get("method")
            body = list_payload if method == "list" else meta_payload
            resp = Mock()
            resp.status_code = 200
            resp.json.return_value = body
            resp.raise_for_status = Mock()
            return resp
        dl_attempts["n"] += 1
        if dl_attempts["n"] < 3:
            raise requests.exceptions.ConnectTimeout("connect timed out")
        resp = Mock()
        resp.status_code = 200
        resp.content = b"parquet-bytes"
        resp.raise_for_status = Mock()
        return resp

    monkeypatch.setattr(baidu_books.requests, "get", fake_get)
    monkeypatch.setattr(baidu_books.time, "sleep", lambda *_args, **_kwargs: None)

    payload = baidu_books.download_book_bytes("20251105", "600000.SH", "行情")
    assert payload == b"parquet-bytes"
    assert dl_attempts["n"] == 3


def test_dir_listed_once_for_three_file_types(monkeypatch: pytest.MonkeyPatch):
    """同一股票目录下三类文件只列一次父目录。"""
    from app.services.level2_factors import baidu_books

    list_calls = {"n": 0}
    files = [
        {"server_filename": "行情.parquet", "isdir": 0, "fs_id": 1},
        {"server_filename": "逐笔成交.parquet", "isdir": 0, "fs_id": 2},
        {"server_filename": "逐笔委托.parquet", "isdir": 0, "fs_id": 3},
    ]

    def fake_get(url, params=None, headers=None, allow_redirects=True, timeout=None):
        method = (params or {}).get("method")
        resp = Mock()
        resp.status_code = 200
        resp.raise_for_status = Mock()
        if method == "list":
            list_calls["n"] += 1
            resp.json.return_value = {"errno": 0, "list": files}
            return resp
        if method == "filemetas":
            resp.json.return_value = {"errno": 0, "list": [{"dlink": "https://d.pcs.baidu.com/f"}]}
            return resp
        resp.content = b"x"
        return resp

    monkeypatch.setattr(baidu_books.requests, "get", fake_get)
    for ftype in ("行情", "逐笔成交", "逐笔委托"):
        assert baidu_books.download_book_bytes("20251105", "600000.SH", ftype) == b"x"
    assert list_calls["n"] == 1


def test_missing_file_returns_none(monkeypatch: pytest.MonkeyPatch):
    """目录里没有该文件时返回 None，不抛网络异常。"""
    from app.services.level2_factors import baidu_books

    def fake_get(url, params=None, headers=None, allow_redirects=True, timeout=None):
        resp = Mock()
        resp.status_code = 200
        resp.raise_for_status = Mock()
        resp.json.return_value = {"errno": 0, "list": []}
        return resp

    monkeypatch.setattr(baidu_books.requests, "get", fake_get)
    assert baidu_books.download_book_bytes("20251105", "600000.SH", "行情") is None


def test_transient_exhausted_is_raised(monkeypatch: pytest.MonkeyPatch):
    """重试耗尽后把连接错误抛给上层，不再伪装成缺文件。"""
    from app.services.level2_factors import baidu_books

    def fake_get(url, params=None, headers=None, allow_redirects=True, timeout=None):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(baidu_books.requests, "get", fake_get)
    monkeypatch.setattr(baidu_books.time, "sleep", lambda *_args, **_kwargs: None)
    with pytest.raises(requests.exceptions.ConnectionError):
        baidu_books.download_book_bytes("20251105", "600000.SH", "行情")


def test_http_calls_are_serial(monkeypatch: pytest.MonkeyPatch):
    """同一时刻只有一个百度 HTTP。"""
    from app.services.level2_factors import baidu_books

    state = {"n": 0, "peak": 0}
    guard = threading.Lock()

    def fake_get(url, params=None, headers=None, allow_redirects=True, timeout=None):
        with guard:
            state["n"] += 1
            state["peak"] = max(state["peak"], state["n"])
        try:
            baidu_books.time.sleep(0.02)
            resp = Mock()
            resp.status_code = 200
            resp.raise_for_status = Mock()
            if "pan.baidu.com" in str(url):
                method = (params or {}).get("method")
                if method == "list":
                    name = str((params or {}).get("dir") or "").rsplit("/", 1)[-1]
                    fname = "行情.parquet"
                    resp.json.return_value = {
                        "errno": 0,
                        "list": [{"server_filename": fname, "isdir": 0, "fs_id": hash(name) % 100000}],
                    }
                    return resp
                resp.json.return_value = {"errno": 0, "list": [{"dlink": "https://d.pcs.baidu.com/f"}]}
                return resp
            resp.content = b"x"
            return resp
        finally:
            with guard:
                state["n"] -= 1

    monkeypatch.setattr(baidu_books.requests, "get", fake_get)
    threads = [
        threading.Thread(target=baidu_books.download_book_bytes, args=("20251105", code, "行情"))
        for code in ("600000.SH", "000001.SZ")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert state["peak"] == 1


def test_circuit_breaker_sleeps_after_connect_failures(monkeypatch: pytest.MonkeyPatch):
    """连续连接失败达到阈值后休眠一次。"""
    from app.services.level2_factors import baidu_books

    monkeypatch.setattr(baidu_books, "_BREAKER_THRESHOLD", 3)
    sleeps: list[float] = []
    monkeypatch.setattr(baidu_books.time, "sleep", lambda sec: sleeps.append(sec))

    def fake_get(url, params=None, headers=None, allow_redirects=True, timeout=None):
        raise requests.exceptions.ConnectTimeout("no route")

    monkeypatch.setattr(baidu_books.requests, "get", fake_get)
    with pytest.raises(requests.exceptions.ConnectTimeout):
        baidu_books.download_book_bytes("20251105", "600000.SH", "行情")
    assert baidu_books._BREAKER_SLEEP_SEC in sleeps


def test_refresh_token_writes_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """刷新成功后把新令牌写回 .env，并保留无关配置。"""
    from app.services.level2_factors import baidu_books

    env = tmp_path / ".env"
    env.write_text(
        "BAIDU_ACCESS_TOKEN=old\nBAIDU_REFRESH_TOKEN=r1\nOTHER=1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(baidu_books, "_env_path", lambda: env)
    monkeypatch.setenv("BAIDU_REFRESH_TOKEN", "r1")
    monkeypatch.setenv("BAIDU_APP_KEY", "app")
    monkeypatch.setenv("BAIDU_SECRET_KEY", "sec")

    def fake_get(url, params=None, headers=None, allow_redirects=True, timeout=None):
        resp = Mock()
        resp.status_code = 200
        resp.raise_for_status = Mock()
        resp.json.return_value = {"access_token": "new-access", "refresh_token": "new-refresh"}
        return resp

    monkeypatch.setattr(baidu_books.requests, "get", fake_get)
    assert baidu_books._refresh_token("old") == "new-access"
    text = env.read_text(encoding="utf-8")
    assert "BAIDU_ACCESS_TOKEN=new-access" in text
    assert "BAIDU_REFRESH_TOKEN=new-refresh" in text
    assert "OTHER=1" in text
    assert baidu_books.os.environ["BAIDU_ACCESS_TOKEN"] == "new-access"
