"""D1 Worker HTTP 客户端契约。"""
from __future__ import annotations

import pytest

from app.services.level2_factors import d1_client


def test_configured_requires_url_and_token(monkeypatch):
    monkeypatch.delenv("D1_WORKER_URL", raising=False)
    monkeypatch.delenv("D1_WORKER_TOKEN", raising=False)
    assert d1_client.configured() is False
    monkeypatch.setenv("D1_WORKER_URL", "https://example.workers.dev")
    assert d1_client.configured() is False
    monkeypatch.setenv("D1_WORKER_TOKEN", "secret")
    assert d1_client.configured() is True


def test_query_posts_bearer_and_parses_rows(monkeypatch):
    monkeypatch.setenv("D1_WORKER_URL", "https://example.workers.dev")
    monkeypatch.setenv("D1_WORKER_TOKEN", "secret")

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "ok": True,
                "results": [{"results": [{"trade_date": "20251009", "n": 1}], "success": True}],
            }

    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return _Resp()

    monkeypatch.setattr(d1_client.requests, "post", fake_post)
    rows = d1_client.query("SELECT 1 AS n", [])
    assert seen["url"] == "https://example.workers.dev/v1/query"
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert rows == [{"trade_date": "20251009", "n": 1}]


def test_batch_rejects_oversize(monkeypatch):
    monkeypatch.setenv("D1_WORKER_URL", "https://example.workers.dev")
    monkeypatch.setenv("D1_WORKER_TOKEN", "secret")
    statements = [{"sql": "SELECT 1", "params": []}] * (d1_client.MAX_BATCH_STATEMENTS + 1)
    with pytest.raises(d1_client.D1WorkerError):
        d1_client.batch(statements)


def test_http_error_raises(monkeypatch):
    monkeypatch.setenv("D1_WORKER_URL", "https://example.workers.dev")
    monkeypatch.setenv("D1_WORKER_TOKEN", "secret")

    class _Resp:
        status_code = 401

        @staticmethod
        def json():
            return {"ok": False, "error": "unauthorized"}

    monkeypatch.setattr(d1_client.requests, "post", lambda *a, **k: _Resp())
    with pytest.raises(d1_client.D1WorkerError, match="unauthorized"):
        d1_client.query("SELECT 1")


def test_post_retries_transient_connection_error(monkeypatch):
    """网络瞬态失败应退避重试，最终成功。"""
    monkeypatch.setenv("D1_WORKER_URL", "https://example.workers.dev")
    monkeypatch.setenv("D1_WORKER_TOKEN", "secret")
    monkeypatch.setattr(d1_client, "_POST_BACKOFF_SEC", (0, 0, 0, 0))

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "results": [{"results": [{"n": 1}], "success": True}]}

    calls = {"n": 0}

    def flaky_post(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise d1_client.requests.ConnectionError("boom")
        return _Resp()

    monkeypatch.setattr(d1_client.requests, "post", flaky_post)
    rows = d1_client.query("SELECT 1 AS n")
    assert calls["n"] == 3
    assert rows == [{"n": 1}]
