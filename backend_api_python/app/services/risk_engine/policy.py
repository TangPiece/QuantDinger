"""RiskPolicy 装载 / 校验。"""

from __future__ import annotations

from typing import Any, Mapping

from .hash import compute_policy_hash
from .protocol import RiskPolicy


def finalize_policy(policy: RiskPolicy) -> RiskPolicy:
    """补齐 policy_hash。"""
    h = compute_policy_hash(policy)
    if not policy.policy_hash or policy.policy_hash != h:
        return policy.model_copy(update={"policy_hash": h})
    return policy


def from_bundle_meta(meta: Mapping[str, Any] | None = None) -> RiskPolicy:
    """从 Bundle / runtime metadata 构造策略（缺省用安全默认）。"""
    m = dict(meta or {})
    if m.get("max_single_position_weight") is not None:
        max_single = float(m["max_single_position_weight"])
    elif m.get("max_single_weight") is not None:
        max_single = float(m["max_single_weight"])
    else:
        max_single = 0.10

    if m.get("signal_ttl_seconds") is not None:
        signal_ttl = float(m["signal_ttl_seconds"])
    elif m.get("stale_after_hours") is not None:
        signal_ttl = float(m["stale_after_hours"]) * 3600.0
    else:
        signal_ttl = 172800.0

    p = RiskPolicy(
        policy_code=str(m.get("risk_policy_code") or m.get("policy_code") or "default"),
        policy_version=str(
            m.get("risk_policy_version") or m.get("policy_version") or "1"
        ),
        max_single_position_weight=max_single,
        max_gross_exposure=float(m.get("max_gross_exposure") or 1.0),
        max_turnover=float(m.get("max_turnover") or 0.30),
        max_position_delta_weight=float(m.get("max_position_delta_weight") or 0.05),
        data_freshness_seconds=float(m.get("data_freshness_seconds") or 86400.0),
        signal_ttl_seconds=signal_ttl,
        require_universe=bool(m.get("require_universe") or False),
        universe_membership=list(m.get("universe_membership") or []),
        short_allowed=bool(m.get("short_allowed") or False),
        clip_on_limit=bool(
            m["clip_on_limit"] if m.get("clip_on_limit") is not None else True
        ),
        metadata={k: v for k, v in m.items() if str(k).startswith("risk_")},
    )
    return finalize_policy(p)


def parse_policy_ref(ref: str) -> tuple[str, str]:
    """code@version。"""
    text = str(ref or "").strip()
    if "@" not in text:
        raise ValueError(f"policy_ref must be code@version, got {ref!r}")
    code, ver = text.split("@", 1)
    if not code or not ver:
        raise ValueError(f"policy_ref must be code@version, got {ref!r}")
    return code, ver
