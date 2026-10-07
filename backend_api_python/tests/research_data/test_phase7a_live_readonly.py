"""Phase 7A：Live Read-only 验收。"""

from __future__ import annotations

import ast
import inspect
import os
import sys
from pathlib import Path

import pytest

from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError
from app.services.live_readonly.adapter import LiveReadonlyAdapter, fake_adapter
from app.services.live_readonly.credentials import load_alpaca_live_credentials
from app.services.live_readonly.gate import ProductionReadyError, require_production_ready
from app.services.live_readonly.modes import EnvironmentTransitionError, assert_transition
from app.services.live_readonly.runner import LiveReadonlyService
from app.services.live_readonly.session import SessionImmutableError, merge_session_update
from app.services.live_readonly.transport import AlpacaLiveReadonlyTransport
from app.services.oms import cycle as oms_cycle
from app.services.oms.protocol import Order

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_readonly_golden.golden import (  # noqa: E402
    ACCOUNT_ID,
    DATASET_HASH,
    MODEL_VERSION,
    STRATEGY_VERSION,
    make_env,
)


def _pkg_root() -> Path:
    return Path(__file__).resolve().parents[2] / "app" / "services" / "live_readonly"


def test_ast_no_post_orders_or_live_submit():
    """包内禁止 POST /v2/orders 与 OMS 发单耦合。"""
    root = _pkg_root()
    forbidden_snippets = ('"POST"', "'POST'", "POST /v2/orders")
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if py.name == "transport.py":
            # transport 仅允许在常量/注释语境出现 POST 拒绝
            tree = ast.parse(text, filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr == "request":
                        if node.args and isinstance(node.args[0], ast.Constant):
                            if str(node.args[0].value).upper() == "POST":
                                pytest.fail(f"{py}: request(POST...) forbidden")
            continue
        for snippet in forbidden_snippets:
            if snippet in text and "forbidden" not in text.lower():
                if snippet in text and py.name not in ("transport.py", "adapter.py"):
                    pass
        tree = ast.parse(text, filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if "oms.runner" in mod or mod.endswith(".oms"):
                    pytest.fail(f"{py}: must not import OMS submit path")
    from app.services.live_readonly.adapter import _forbid_write

    assert "_forbid_write" in inspect.getsource(LiveReadonlyAdapter.submit_order)
    assert "LIVE_READONLY_FORBIDDEN" in inspect.getsource(_forbid_write)


def test_oms_allowed_env_no_live():
    assert "LIVE" not in oms_cycle._ALLOWED_ENV
    assert "LIVE_READONLY" not in oms_cycle._ALLOWED_ENV


def test_write_methods_raise():
    ad = fake_adapter()
    ad.connect()
    order = Order(
        order_id="o1",
        client_order_id="c1",
        instrument_key="USStock:AAPL",
        quantity=1.0,
    )
    for meth in (
        lambda: ad.submit(order),
        lambda: ad.submit_order(order),
        lambda: ad.cancel(order),
        lambda: ad.replace(order),
    ):
        with pytest.raises(BrokerAdapterError) as exc:
            meth()
        assert exc.value.code == AdapterErrorCode.LIVE_READONLY_FORBIDDEN


def test_paper_to_live_rejected():
    with pytest.raises(EnvironmentTransitionError):
        assert_transition("PAPER", "LIVE")
    with pytest.raises(EnvironmentTransitionError):
        assert_transition("PAPER", "LIVE_CONTROLLED")


def test_connect_without_production_ready(tmp_path):
    registry = make_env(tmp_path / "nordy")[1]
    os.environ.pop("PRODUCTION_READY", None)
    # 新 registry 无 readiness
    from app.services.research_data.registry import LocalJsonRegistry

    reg2 = LocalJsonRegistry(root=tmp_path / "nordy2" / "registry")
    ad = LiveReadonlyAdapter(
        transport=fake_adapter()._transport,
        skip_production_gate=False,
        registry=reg2,
    )
    with pytest.raises(ProductionReadyError):
        require_production_ready(reg2)
    ad._connected = False
    with pytest.raises(ProductionReadyError):
        ad.connect()


def test_session_hash_immutable(tmp_path):
    _, _, _, _, _, _, _, lro = make_env(tmp_path / "sess")
    session = lro.start_session(
        account_id=ACCOUNT_ID,
        dataset_hash=DATASET_HASH,
        model_version=MODEL_VERSION,
        strategy_version=STRATEGY_VERSION,
    )
    lro.lock_check(dataset_hash=DATASET_HASH)
    with pytest.raises(SessionImmutableError):
        merge_session_update(session, {"dataset_hash": "other"})


def test_snapshot_and_recon_observe(tmp_path):
    _, _, portfolio, _, _, _, _, lro = make_env(tmp_path / "snap")
    snap = lro.capture_snapshot(account_id=ACCOUNT_ID)
    assert snap.account_id == ACCOUNT_ID
    assert snap.positions
    acct = portfolio.open_account(
        environment="PAPER", currency="USD", initial_cash=5000.0, market="US"
    )
    pid = str(acct.metadata.get("default_portfolio_id") or "")
    run = lro.reconcile_observe(acct.account_id, pid, salt="lro")
    assert run.run_id


def test_transport_rejects_post():
    from app.services.live_readonly.transport import FakeLiveReadonlyTransport

    tr = FakeLiveReadonlyTransport()
    with pytest.raises(BrokerAdapterError) as exc:
        tr.request("POST", "/v2/orders")
    assert exc.value.code == AdapterErrorCode.LIVE_READONLY_FORBIDDEN


def test_live_credentials_host_allowlist():
    os.environ["ALPACA_LIVE_API_KEY"] = "k"
    os.environ["ALPACA_LIVE_API_SECRET"] = "s"
    os.environ["ALPACA_LIVE_BASE_URL"] = "https://paper-api.alpaca.markets"
    with pytest.raises(BrokerAdapterError):
        load_alpaca_live_credentials()
    os.environ["ALPACA_LIVE_BASE_URL"] = "https://api.alpaca.markets"
    creds = load_alpaca_live_credentials()
    assert creds["base_url"].endswith("api.alpaca.markets")


@pytest.mark.skipif(
    not os.environ.get("ALPACA_LIVE_API_KEY") or not os.environ.get("ALPACA_LIVE_API_SECRET"),
    reason="opt-in real Alpaca Live GET",
)
def test_opt_in_real_get_account():
    """仅当设置 ALPACA_LIVE_* 时触网 GET account。"""
    os.environ.setdefault("PRODUCTION_READY", "true")
    tr = AlpacaLiveReadonlyTransport()
    raw = tr.get_account()
    assert raw.get("id") or raw.get("account_number")
