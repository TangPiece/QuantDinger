"""Phase 7E：Scale / LIVE_ENV / STRATEGY_GO_LIVE 审批审计（token 仅存 hash）。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from .protocol import ApprovalKind, ApprovalStatus, GovernanceApproval, ScaleLevel


def hash_approval_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()[:32]


def new_approval(
    *,
    kind: ApprovalKind,
    strategy_id: str = "",
    account_id: str = "",
    operator_actor: str = "",
    approval_token: str = "",
    from_scale: ScaleLevel | str = "",
    to_scale: ScaleLevel | str = "",
    status: ApprovalStatus = "PENDING",
) -> GovernanceApproval:
    return GovernanceApproval(
        approval_id="govappr_" + uuid4().hex[:16],
        kind=kind,
        strategy_id=strategy_id,
        account_id=account_id,
        operator_actor=operator_actor,
        approval_token_hash=hash_approval_token(approval_token),
        status=status,
        from_scale=str(from_scale),
        to_scale=str(to_scale),
        approved_at=datetime.now(timezone.utc).isoformat()
        if status == "APPROVED"
        else "",
    )


def approve_record(rec: GovernanceApproval, *, operator: str, token: str = "") -> GovernanceApproval:
    return rec.model_copy(
        update={
            "status": "APPROVED",
            "operator_actor": operator or rec.operator_actor,
            "approval_token_hash": hash_approval_token(token or rec.approval_token_hash),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
    )
