"""LightGBMModelAdapter：唯一允许的 Qlib LGBModel 入口。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .specs import default_lgb_config


class ModelTrainingError(RuntimeError):
    """训练 / 预测失败。"""


def lightgbm_runtime_available() -> bool:
    """import 成功且 native lib 可加载（macOS 需 libomp）。"""
    try:
        import lightgbm  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


def _require_lightgbm() -> None:
    try:
        import lightgbm  # noqa: F401
    except OSError as exc:
        raise ModelTrainingError(
            "lightgbm unavailable (macOS: brew install libomp); "
            f"underlying: {exc}"
        ) from exc
    except ImportError as exc:
        raise ModelTrainingError("lightgbm not installed") from exc


class LightGBMModelAdapter:
    """封装 qlib.contrib.model.gbdt.LGBModel。"""

    ENGINE = "lightgbm"

    def create_model(self, config: dict[str, Any]) -> Any:
        """构造 LGBModel；合并默认超参。"""
        _require_lightgbm()
        from qlib.contrib.model.gbdt import LGBModel

        cfg = {**default_lgb_config(), **dict(config or {})}
        loss = cfg.pop("loss", "mse")
        early_stopping_rounds = cfg.pop("early_stopping_rounds", 50)
        num_boost_round = cfg.pop("num_boost_round", 1000)
        # 其余键作为 LightGBM params（含 seed / learning_rate 等）
        return LGBModel(
            loss=loss,
            early_stopping_rounds=early_stopping_rounds,
            num_boost_round=num_boost_round,
            **cfg,
        )

    def fit(self, model: Any, dataset: Any) -> None:
        """仅在 train（及 qlib 内部 valid early-stop）上 fit。"""
        model.fit(dataset, verbose_eval=0)

    def predict(self, model: Any, dataset: Any, segment: str = "test") -> pd.Series:
        if model.model is None:
            raise ModelTrainingError("model is not fitted")
        return model.predict(dataset, segment=segment)

    def evaluate_valid(self, model: Any, dataset: Any) -> dict[str, float]:
        """Valid 段 MSE / rank IC（不参与 refit）。"""
        from qlib.data.dataset.handler import DataHandlerLP

        df = dataset.prepare(
            "valid",
            col_set=["feature", "label"],
            data_key=DataHandlerLP.DK_I,
        )
        if df is None or len(df) == 0:
            return {"valid_mse": float("nan"), "valid_ic": float("nan"), "valid_rows": 0.0}
        x = df["feature"]
        y = df["label"]
        if hasattr(y, "values") and y.values.ndim == 2:
            y_arr = np.squeeze(y.values)
        else:
            y_arr = np.asarray(y).ravel()
        pred = model.model.predict(x.values)
        mse = float(np.mean((pred - y_arr) ** 2))
        ic = float(pd.Series(pred).corr(pd.Series(y_arr), method="spearman"))
        if np.isnan(ic):
            ic = 0.0
        return {
            "valid_mse": mse,
            "valid_ic": ic,
            "valid_rows": float(len(pred)),
        }

    def save_booster_bytes(self, model: Any) -> bytes:
        """序列化 booster 为二进制（供 artifact 落盘）。"""
        import tempfile
        from pathlib import Path

        if model.model is None:
            raise ModelTrainingError("model is not fitted")
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            model.model.save_model(str(path))
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)
