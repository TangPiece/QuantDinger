"""实验复现指纹（内容寻址 experiment_id 输入）。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json
from app.services.research_data.model_training.version import MODEL_TRAINER_VERSION
from app.services.research_data.signal.version import SIGNAL_PIPELINE_VERSION

from .version import EXPERIMENT_PIPELINE_VERSION


def compute_repro_fingerprint(
    *,
    dataset_hash: str,
    bundle_hash: str,
    model_ref: str,
    config_digest: str,
    seed: int,
    strategy_digest: str,
    portfolio_digest: str,
    experiment_pipeline_version: str = EXPERIMENT_PIPELINE_VERSION,
    model_trainer_version: str = MODEL_TRAINER_VERSION,
    signal_pipeline_version: str = SIGNAL_PIPELINE_VERSION,
) -> str:
    """同配置同内容 → 同指纹；用于 experiment_id 与 A==B。"""
    payload = "|".join(
        [
            str(dataset_hash),
            str(bundle_hash),
            str(model_ref),
            str(config_digest),
            str(seed),
            str(strategy_digest),
            str(portfolio_digest),
            str(experiment_pipeline_version),
            str(model_trainer_version),
            str(signal_pipeline_version),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def experiment_id_from_fingerprint(repro_fingerprint: str) -> str:
    """内容寻址 experiment_id。"""
    return f"exp_{str(repro_fingerprint)[:32]}"


def digest_payload(obj: dict) -> str:
    """任意 dict 的 canonical sha256（辅助测试）。"""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()
