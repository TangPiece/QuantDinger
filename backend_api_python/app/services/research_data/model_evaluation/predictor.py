"""评估预测面板：inject 或经 ModelPlatformService.predict。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import ModelEvaluationInject, ModelEvaluationRequest


class PredictorError(RuntimeError):
    pass


def build_prediction_rows(
    request: ModelEvaluationRequest,
    *,
    inject: ModelEvaluationInject | None = None,
    model_platform: Any | None = None,
) -> list[dict[str, Any]]:
    inj = inject or ModelEvaluationInject()
    if inj.predictions:
        rows: list[dict[str, Any]] = []
        for raw in inj.predictions:
            rows.append(
                {
                    "date": str(raw.get("date") or raw.get("trading_date") or ""),
                    "instrument": str(
                        raw.get("instrument") or raw.get("instrument_key") or ""
                    ),
                    "prediction": raw.get("prediction"),
                    "label": raw.get("label"),
                    "rank": raw.get("rank"),
                }
            )
        return rows

    if model_platform is None:
        raise PredictorError(
            "predictions required via inject when model_platform is unavailable"
        )

    segments = {
        "train_start": request.evaluation_start,
        "train_end": request.evaluation_start,
        "validation_start": request.evaluation_start,
        "validation_end": request.evaluation_end,
        "test_start": request.evaluation_start,
        "test_end": request.evaluation_end,
    }
    # 需要 dataset_ref；无则失败
    if not (request.dataset_ref or "").strip():
        raise PredictorError("dataset_ref required for live predict")
    try:
        result = model_platform.predict(
            request.model_version_id,
            dataset_ref=request.dataset_ref,
            dataset_hash=request.evaluation_dataset_hash or request.dataset_hash,
            segments=segments,
        )
    except Exception as exc:
        raise PredictorError(str(exc)) from exc

    rows = []
    for row in getattr(result, "rows", []) or []:
        rows.append(
            {
                "date": getattr(row, "trading_date", "") or "",
                "instrument": getattr(row, "instrument", "") or "",
                "prediction": getattr(row, "prediction", None),
                "label": None,
                "rank": None,
            }
        )
    return rows


__all__ = ["PredictorError", "build_prediction_rows"]
