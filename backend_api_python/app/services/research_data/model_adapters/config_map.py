"""QuantDinger TrainingConfig → Qlib/LightGBM 超参。"""

from __future__ import annotations

from typing import Any


def map_training_config_to_lgb(
    model_config: dict[str, Any] | None,
    *,
    hyperparameters: dict[str, Any] | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """声明式 QD config → LGBModel / lightgbm params（无 pickle）。"""
    src = dict(model_config or {})
    params = dict(src.get("parameters") or {})
    out: dict[str, Any] = {}

    # Phase 2D default_lgb_config 风格键
    if "loss" in src:
        out["loss"] = src["loss"]
    elif str(src.get("objective", "")).lower() in ("regression", "mse", ""):
        out["loss"] = "mse"
    elif src.get("objective"):
        out["loss"] = str(src["objective"]).lower()

    if "num_boost_round" in src:
        out["num_boost_round"] = int(src["num_boost_round"])
    early = src.get("early_stopping") or {}
    if isinstance(early, dict) and early.get("rounds") is not None:
        out["early_stopping_rounds"] = int(early["rounds"])
    elif "early_stopping_rounds" in src:
        out["early_stopping_rounds"] = int(src["early_stopping_rounds"])

    for key, val in params.items():
        out[key] = val

    hp = dict(hyperparameters or {})
    for key, val in hp.items():
        if key == "num_boost_round" and "num_boost_round" not in out:
            out["num_boost_round"] = int(val)
        else:
            out[key] = val

    out["seed"] = int(seed)
    # 训练轮次默认偏小，便于 fixture；调用方可覆盖
    out.setdefault("num_boost_round", 8)
    out.setdefault("early_stopping_rounds", 3)
    out.setdefault("learning_rate", 0.05)
    out.setdefault("num_leaves", 8)
    out.setdefault("loss", "mse")
    return out


__all__ = ["map_training_config_to_lgb"]
