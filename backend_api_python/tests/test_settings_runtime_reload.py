"""Tests for settings runtime reload helpers."""

from __future__ import annotations

import signal


def test_signal_workers_reload_env_sends_sighup_to_parent(monkeypatch):
    """Gunicorn siblings need SIGHUP so LLM keys from .env reach every worker."""
    import app.services.settings.runtime as runtime

    calls = []
    monkeypatch.setattr(runtime.os, "getppid", lambda: 4242)
    monkeypatch.setattr(
        runtime.os,
        "kill",
        lambda pid, sig: calls.append((pid, sig)),
    )

    assert runtime.signal_workers_reload_env() is True
    assert calls == [(4242, signal.SIGHUP)]


def test_signal_workers_reload_env_skips_init_parent(monkeypatch):
    import app.services.settings.runtime as runtime

    calls = []
    monkeypatch.setattr(runtime.os, "getppid", lambda: 1)
    monkeypatch.setattr(
        runtime.os,
        "kill",
        lambda pid, sig: calls.append((pid, sig)),
    )

    assert runtime.signal_workers_reload_env() is False
    assert calls == []


def test_signal_workers_reload_env_swallows_kill_errors(monkeypatch):
    import app.services.settings.runtime as runtime

    monkeypatch.setattr(runtime.os, "getppid", lambda: 99)

    def _boom(_pid, _sig):
        raise OSError("not permitted")

    monkeypatch.setattr(runtime.os, "kill", _boom)
    assert runtime.signal_workers_reload_env() is False
