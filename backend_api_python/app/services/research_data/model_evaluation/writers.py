"""写 EvaluationRun 索引与 Bundle 文件。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifact_store import ModelEvaluationArtifactStore
from .protocol import ModelEvaluationRun


def write_run(store: ModelEvaluationArtifactStore, run: ModelEvaluationRun) -> Path:
    path = store.run_path(evaluation_run_id=run.evaluation_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_evaluation_bundle(
    store: ModelEvaluationArtifactStore,
    evaluation_run_id: str,
    *,
    metrics: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
    ranking: Mapping[str, Any] | None = None,
    stability: Mapping[str, Any] | None = None,
    feature_importance: Mapping[str, Any] | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    dest = store.bundle_dir(evaluation_run_id=evaluation_run_id)
    uris: dict[str, str] = {}

    man = dict(manifest or {})
    man.setdefault("evaluation_run_id", evaluation_run_id)
    man_path = dest / "manifest.json"
    man_path.write_text(
        json.dumps(man, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    uris["manifest_uri"] = str(man_path.resolve())

    metrics_path = dest / "metrics.json"
    metrics_path.write_text(
        json.dumps(dict(metrics), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    uris["metrics_uri"] = str(metrics_path.resolve())

    pred_path = dest / "predictions.parquet"
    _write_predictions_parquet(pred_path, predictions)
    uris["prediction_uri"] = str(pred_path.resolve())

    for name, payload in (
        ("ranking.json", ranking),
        ("stability.json", stability),
        ("feature_importance.json", feature_importance or {"status": "SKIPPED"}),
    ):
        p = dest / name
        p.write_text(
            json.dumps(dict(payload or {}), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        uris[name.replace(".json", "_uri")] = str(p.resolve())

    return uris


def _write_predictions_parquet(
    path: Path, rows: Sequence[Mapping[str, Any]]
) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table(
            {
                "date": [str(r.get("date") or "") for r in rows],
                "instrument": [str(r.get("instrument") or "") for r in rows],
                "prediction": [
                    float(r["prediction"]) if r.get("prediction") is not None else None
                    for r in rows
                ],
                "label": [
                    float(r["label"]) if r.get("label") is not None else None
                    for r in rows
                ],
                "rank": [
                    float(r["rank"]) if r.get("rank") is not None else None
                    for r in rows
                ],
            }
        )
        pq.write_table(table, path, compression="zstd")
    except Exception:
        # fallback JSON lines
        alt = path.with_suffix(".json")
        alt.write_text(
            json.dumps(list(rows), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


__all__ = ["write_evaluation_bundle", "write_run"]
