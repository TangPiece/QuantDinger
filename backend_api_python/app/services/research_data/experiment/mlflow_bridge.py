"""MLflow 桥接：QuantDinger Experiment ↔ MLflow Run（失败不阻断）。"""

from __future__ import annotations

import os
from typing import Any, Optional


def log_experiment_run(
    *,
    experiment_name: str,
    experiment_id: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
    tags: dict[str, str] | None = None,
) -> Optional[str]:
    """创建 MLflow run；不可用则返回 None。

    Tags 至少包含 qd.experiment_id / qd.dataset_hash（若 params 有）。
    """
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError:
        return None
    try:
        tracking = os.environ.get("MLFLOW_TRACKING_URI") or "file:./mlruns"
        # 强制回到调用方指定的 tracking（Qlib 可能改写默认 URI）
        mlflow.set_tracking_uri(tracking)
        # Qlib Recorder 可能残留 active run
        for _ in range(5):
            if mlflow.active_run() is None:
                break
            try:
                mlflow.end_run()
            except Exception:
                break
        client = MlflowClient(tracking_uri=tracking)
        exp = client.get_experiment_by_name(experiment_name)
        if exp is None:
            exp_id = client.create_experiment(experiment_name)
        else:
            exp_id = exp.experiment_id
        run = client.create_run(experiment_id=exp_id)
        run_id = run.info.run_id
        tag_map = {"qd.experiment_id": experiment_id}
        if params.get("dataset_hash"):
            tag_map["qd.dataset_hash"] = str(params["dataset_hash"])[:250]
        if tags:
            tag_map.update({str(k): str(v)[:250] for k, v in tags.items()})
        for k, v in tag_map.items():
            client.set_tag(run_id, k, v)
        for k, v in params.items():
            client.log_param(run_id, str(k)[:250], str(v)[:250])
        for k, v in metrics.items():
            if isinstance(v, (int, float)) and v == v:  # 非 NaN
                client.log_metric(run_id, str(k), float(v))
        client.set_terminated(run_id)
        return run_id
    except Exception:
        return None
