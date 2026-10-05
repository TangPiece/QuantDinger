"""可选 MLflow 挂接：写 tags/metrics；失败不阻断回测。"""

from __future__ import annotations

import os
from typing import Any, Optional

from app.services.research_data.backtest.result import BacktestResult


def log_backtest_to_mlflow(
    result: BacktestResult,
    *,
    mlflow_run_id: str | None = None,
    experiment_name: str = "quantdinger_backtest",
    extra_tags: dict[str, str] | None = None,
) -> Optional[str]:
    """向已有 run 或新 run 写入回测 tags/metrics；失败返回 None。"""
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError:
        return None

    metrics: dict[str, Any] = {}
    m = result.metrics
    for key in (
        "total_return",
        "annualized_return",
        "volatility",
        "sharpe",
        "max_drawdown",
        "turnover",
        "calmar",
    ):
        val = getattr(m, key, None)
        if isinstance(val, (int, float)) and val == val:
            metrics[f"bt_{key}"] = float(val)

    tags = {
        "qd.backtest.result_id": result.result_id,
        "qd.backtest.engine": result.engine,
        "qd.experiment_id": result.experiment_id,
        "qd.dataset_hash": result.dataset_hash,
        "qd.request_fingerprint": result.request_fingerprint[:64],
    }
    if result.engine_version:
        tags["qd.backtest.engine_version"] = result.engine_version
    if extra_tags:
        tags.update({str(k): str(v)[:250] for k, v in extra_tags.items()})

    try:
        tracking = os.environ.get("MLFLOW_TRACKING_URI") or "file:./mlruns"
        mlflow.set_tracking_uri(tracking)
        client = MlflowClient(tracking_uri=tracking)
        run_id = mlflow_run_id
        if run_id:
            # 向已有 experiment run 追加
            for k, v in tags.items():
                client.set_tag(run_id, k, str(v)[:250])
            for k, v in metrics.items():
                client.log_metric(run_id, str(k), float(v))
            return run_id

        exp = client.get_experiment_by_name(experiment_name)
        if exp is None:
            exp_id = client.create_experiment(experiment_name)
        else:
            exp_id = exp.experiment_id
        run = client.create_run(experiment_id=exp_id)
        run_id = run.info.run_id
        for k, v in tags.items():
            client.set_tag(run_id, k, str(v)[:250])
        for k, v in metrics.items():
            client.log_metric(run_id, str(k), float(v))
        client.set_terminated(run_id)
        return run_id
    except Exception:
        return None
