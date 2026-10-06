"""Phase 6I：dataset_hash / strategy_version / trace_id 贯通 Intent 与 Order。"""

from __future__ import annotations

from typing import Any, Sequence

from app.services.ops_service.trace import ensure_trace_id
from app.services.research_data.contracts import OrderIntent, TargetPosition


class IdentityError(ValueError):
    """Identity 链校验失败。"""


def stamp_targets(
    targets: Sequence[TargetPosition],
    *,
    dataset_hash: str,
    strategy_version: str,
    strategy_id: str = "",
) -> list[TargetPosition]:
    """为 TargetPosition 写入研究身份字段。"""
    out: list[TargetPosition] = []
    for t in targets:
        out.append(
            t.model_copy(
                update={
                    "dataset_hash": dataset_hash or t.dataset_hash,
                    "strategy_version": strategy_version or t.strategy_version,
                }
            )
        )
    return out


def stamp_intents(
    intents: Sequence[OrderIntent],
    *,
    dataset_hash: str,
    strategy_version: str,
    strategy_id: str = "",
    trace_seed: str = "",
) -> list[OrderIntent]:
    """补齐 trace_id 与 strategy_version；dataset_hash 写入 reason 前缀供审计。"""
    stamped: list[OrderIntent] = []
    for idx, intent in enumerate(intents):
        tid = ensure_trace_id(intent, seed=trace_seed or f"e2e|{idx}")
        sv = strategy_version or str(intent.strategy_version or "")
        prefix = f"e2e|dh={dataset_hash}|sv={sv}|sid={strategy_id}"
        reason = str(intent.reason or "")
        if prefix not in reason:
            reason = f"{prefix}|{reason}" if reason else prefix
        stamped.append(
            intent.model_copy(
                update={
                    "trace_id": tid,
                    "strategy_version": sv or intent.strategy_version,
                    "reason": reason,
                }
            )
        )
    return stamped


def submit_metadata_identity(
    *,
    dataset_hash: str,
    strategy_version: str,
    strategy_id: str = "",
    trace_id: str = "",
    broker_inject: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """合并进 OMS submit metadata，写入 Order.metadata。"""
    meta: dict[str, Any] = {
        "dataset_hash": dataset_hash,
        "strategy_version": strategy_version,
        "strategy_id": strategy_id,
        "e2e_engine": "qd_e2e@1",
    }
    if trace_id:
        meta["trace_id"] = trace_id
    if broker_inject:
        inj = dict(broker_inject)
        # PaperBroker 与 Simulated REST 均读取 inject 键
        meta["simulated"] = inj
        meta["paper_broker"] = inj
    return meta


def validate_order_identity(
    order: Any,
    *,
    dataset_hash: str,
    strategy_version: str,
    trace_id: str = "",
) -> None:
    """校验 Order.metadata 上的身份链。"""
    meta = dict(getattr(order, "metadata", None) or {})
    dh = str(meta.get("dataset_hash") or "")
    if dataset_hash and dh and dh != dataset_hash:
        raise IdentityError(f"dataset_hash drift: {dh!r} != {dataset_hash!r}")
    sv = str(meta.get("strategy_version") or "")
    if strategy_version and sv and sv != strategy_version:
        raise IdentityError(f"strategy_version drift: {sv!r}")
    if trace_id:
        ot = str(meta.get("trace_id") or "")
        if ot and ot != trace_id:
            raise IdentityError(f"trace_id mismatch on order")


def validate_intents_identity(
    intents: Sequence[OrderIntent],
    *,
    dataset_hash: str,
    strategy_version: str,
) -> None:
    """Intent 上必须携带 strategy_version 与 dataset_hash 痕迹。"""
    for intent in intents:
        sv = str(intent.strategy_version or "")
        if strategy_version and sv != strategy_version:
            raise IdentityError(f"intent strategy_version {sv!r}")
        reason = str(intent.reason or "")
        if dataset_hash and f"dh={dataset_hash}" not in reason:
            raise IdentityError("intent missing dataset_hash stamp in reason")
        if not str(intent.trace_id or "").strip():
            raise IdentityError("intent missing trace_id")
