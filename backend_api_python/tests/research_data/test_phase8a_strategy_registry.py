"""Phase 8A：Strategy Registry 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.oms import cycle as oms_cycle
from app.services.strategy_registry.identity import InvalidStrategyIdentityError
from app.services.strategy_registry.protocol import ENGINE_VERSION
from app.services.strategy_registry.runner import VersionImmutableError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategy_registry_golden.golden import (  # noqa: E402
    BUNDLE_HASH,
    STRATEGY_CODE,
    STRATEGY_HASH,
    STRATEGY_VERSION,
    make_registry_env,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_strategy_registry@1"


def test_register_from_fake_bundle(tmp_path):
    svc, registry, _ = make_registry_env(tmp_path / "bundle")
    ver = svc.register_version_from_bundle(
        BUNDLE_HASH,
        strategy_version_label=STRATEGY_VERSION,
        risk_policy_ref="risk_default@v1",
    )
    assert ver.strategy_code == STRATEGY_CODE
    assert ver.bundle_hash == BUNDLE_HASH
    assert ver.dataset_hash
    assert ver.model_version
    assert ver.feature_version
    assert ver.risk_policy_ref == "risk_default@v1"
    assert ver.execution_policy_ref == "NEXT_OPEN"
    assert ver.content_hash


def test_idempotent_register(tmp_path):
    svc, _, _ = make_registry_env(tmp_path / "idem")
    v1 = svc.register_version_from_bundle(
        BUNDLE_HASH,
        strategy_version_label=STRATEGY_VERSION,
        risk_policy_ref="risk_default@v1",
    )
    v2 = svc.register_version_from_bundle(
        BUNDLE_HASH,
        strategy_version_label=STRATEGY_VERSION,
        risk_policy_ref="risk_default@v1",
    )
    assert v1.version_id == v2.version_id
    assert v1.content_hash == v2.content_hash


def test_immutable_pin_reject(tmp_path):
    svc, _, _ = make_registry_env(tmp_path / "immut")
    svc.register_version_from_bundle(BUNDLE_HASH, strategy_version_label=STRATEGY_VERSION)
    with pytest.raises(VersionImmutableError):
        svc.register_version_manual(
            STRATEGY_CODE,
            STRATEGY_VERSION,
            dataset_hash="changed_dh",
            strategy_hash=STRATEGY_HASH,
            bundle_hash=BUNDLE_HASH,
        )


def test_resolve_code_and_bundle(tmp_path):
    svc, _, _ = make_registry_env(tmp_path / "resolve")
    registered = svc.register_version_from_bundle(
        BUNDLE_HASH, strategy_version_label=STRATEGY_VERSION
    )
    by_code = svc.resolve(code=STRATEGY_CODE, version=STRATEGY_VERSION)
    by_bundle = svc.resolve(bundle_hash=BUNDLE_HASH)
    assert by_code.version_id == registered.version_id
    assert by_bundle.version_id == registered.version_id


def test_normalize_strategy_code_reject(tmp_path):
    svc, _, _ = make_registry_env(tmp_path / "bad_code")
    with pytest.raises(InvalidStrategyIdentityError):
        svc.register_strategy("INVALID CODE!")


def test_link_governance_active(tmp_path):
    svc, registry, gov = make_registry_env(tmp_path / "gov")
    svc.register_version_from_bundle(BUNDLE_HASH, strategy_version_label=STRATEGY_VERSION)
    svc.link_governance_active(STRATEGY_CODE, STRATEGY_VERSION)
    active = svc.get_active(STRATEGY_CODE)
    assert active is not None
    assert active.strategy_version == STRATEGY_VERSION
    lc = registry.get_strategy_registry(STRATEGY_CODE)
    assert lc.active_version == STRATEGY_VERSION
    gov_lc = (registry._read() if hasattr(registry, "_read") else {}).get(
        "gov_strategy_lifecycle", {}
    )
    if gov_lc:
        row = gov_lc.get(STRATEGY_CODE)
        assert row and row.get("active_version") == STRATEGY_VERSION


def test_set_policy_bindings_immutable_after_register(tmp_path):
    svc, _, _ = make_registry_env(tmp_path / "policy")
    svc.register_version_from_bundle(BUNDLE_HASH, strategy_version_label=STRATEGY_VERSION)
    with pytest.raises(VersionImmutableError):
        svc.set_policy_bindings(STRATEGY_CODE, STRATEGY_VERSION, risk_ref="other@v2")


def test_no_oms_submit_in_registry_package():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "strategy_registry"
    forbidden = ("submit_order", "oms_cycle.submit", "promote_to_live")
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        for token in forbidden:
            assert token not in text
    assert "LIVE" in oms_cycle._ALLOWED_ENV  # OMS 未改默认；8A 不接线 submit
