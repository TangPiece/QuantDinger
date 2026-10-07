"""Phase 7A：PRODUCTION_READY 门禁 + 环境转换 Audit。"""

from __future__ import annotations

import os
from typing import Any, Optional

from app.services.research_data.registry import ResearchRegistry

from .modes import assert_transition, normalize_environment
from .protocol import TradingEnvironment


class ProductionReadyError(RuntimeError):
    """未通过 6J 生产就绪门禁。"""


def _env_production_ready() -> bool:
    v = (os.environ.get("PRODUCTION_READY") or "").strip().lower()
    return v in ("true", "1", "yes", "on")


def production_ready_from_registry(registry: ResearchRegistry | None) -> bool:
    """扫描 Registry 中 readiness_run 是否曾标记 production_ready。"""
    if registry is None:
        return False
    checker = getattr(registry, "has_production_ready_run", None)
    if callable(checker):
        return bool(checker())
    return False


def is_production_ready(registry: ResearchRegistry | None = None) -> bool:
    """PRODUCTION_READY：环境变量优先，否则 Registry readiness。"""
    if _env_production_ready():
        return True
    return production_ready_from_registry(registry)


def require_production_ready(registry: ResearchRegistry | None = None) -> None:
    """Connect / 进入 LIVE_READONLY 前必须满足。"""
    if not is_production_ready(registry):
        raise ProductionReadyError(
            "PRODUCTION_READY=true required (env or registry readiness_run)"
        )


def transition_environment(
    *,
    from_env: str,
    to_env: str,
    registry: ResearchRegistry | None = None,
    ops_service: Any = None,
    account_id: str = "",
    actor: str = "system",
) -> TradingEnvironment:
    """环境阶梯转换；可选写入 Ops Audit（不含密钥）。"""
    ready = is_production_ready(registry)
    dst = assert_transition(from_env, to_env, production_ready=ready)
    src = normalize_environment(from_env)

    if ops_service is not None:
        try:
            from app.services.ops_service.protocol import AuditActor

            ops_service.emit_audit(
                event_type="ENV_TRANSITION",
                actor=AuditActor(actor_type="OPERATOR", actor_id=actor),
                account_id=account_id,
                entity_type="TRADING_ENVIRONMENT",
                entity_id=account_id or "global",
                before={"environment": src},
                after={"environment": dst},
                reason="live_readonly_gate",
                metadata={"production_ready": ready},
            )
        except Exception:
            pass

    return dst
