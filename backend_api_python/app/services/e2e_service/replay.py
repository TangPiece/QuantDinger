"""Phase 6I：确定性 Replay（同 fixture → 同 intent 指纹）。"""

from __future__ import annotations

from typing import Any, Callable

from .hash import intent_fingerprint
from .protocol import ReplayRequest, ReplayResult, ScenarioSpec


def run_replay(
    request: ReplayRequest,
    *,
    run_once: Callable[[ScenarioSpec, str], str],
    get_spec: Callable[[str], ScenarioSpec],
) -> ReplayResult:
    """两次运行同一 fixture，比对 intent_fingerprint。"""
    spec = get_spec(request.scenario_id)
    spec = spec.model_copy(
        update={
            "fixture_id": request.fixture_id or spec.fixture_id,
            "metadata": {
                **dict(spec.metadata or {}),
                **dict(request.config or {}),
                "dataset_hash": request.dataset_hash,
                "strategy_version": request.strategy_version,
                "replay": True,
            },
        }
    )
    fp1 = run_once(spec, request.dataset_hash)
    fp2 = run_once(spec, request.dataset_hash)
    drift = fp1 != fp2
    return ReplayResult(
        ok=not drift and bool(fp1),
        first_fingerprint=fp1,
        second_fingerprint=fp2,
        drift_detected=drift,
        messages=[] if not drift else ["intent fingerprint drift detected"],
    )
