"""Offline / Online Feature Parity（共享同一取值逻辑）。"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .protocol import FeatureParityReport

# 共享求值器：offline / online 调用同一函数，避免两套业务逻辑
FeatureEvalFn = Callable[[Mapping[str, Any]], float | None]


def default_score_evaluator(row: Mapping[str, Any]) -> float | None:
    """默认：取 score / value / factor_value。"""
    for k in ("score", "value", "factor_value", "online_value", "offline_value"):
        if k in row and row[k] is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                return None
    return None


class OfflineFeatureEvaluator:
    """从物化 / 注入 panel 取值。"""

    def __init__(self, evaluate: FeatureEvalFn | None = None) -> None:
        self._eval = evaluate or default_score_evaluator

    def evaluate_rows(
        self, rows: Sequence[Mapping[str, Any]]
    ) -> dict[tuple[str, str], float]:
        out: dict[tuple[str, str], float] = {}
        for r in rows:
            key = _row_key(r)
            if not key:
                continue
            v = self._eval(r)
            if v is None or v != v:
                continue
            out[key] = float(v)
        return out


class OnlineFeatureEvaluator:
    """as-of 重算：v1 与 Offline 共享同一 evaluate 函数（保证定义同源）。"""

    def __init__(self, evaluate: FeatureEvalFn | None = None) -> None:
        self._eval = evaluate or default_score_evaluator

    def evaluate_rows(
        self, rows: Sequence[Mapping[str, Any]]
    ) -> dict[tuple[str, str], float]:
        out: dict[tuple[str, str], float] = {}
        for r in rows:
            key = _row_key(r)
            if not key:
                continue
            # 允许 online_* 字段优先；否则同一公式
            payload = dict(r)
            if "online_value" in payload:
                payload["score"] = payload["online_value"]
            v = self._eval(payload)
            if v is None or v != v:
                continue
            out[key] = float(v)
        return out


def run_feature_parity(
    offline_rows: Sequence[Mapping[str, Any]],
    online_rows: Sequence[Mapping[str, Any]] | None = None,
    *,
    abs_tol: float = 1e-8,
    rel_tol: float = 1e-6,
    evaluate: FeatureEvalFn | None = None,
) -> FeatureParityReport:
    """比较 offline vs online；未提供 online_rows 时对同一 rows 双跑（恒等）。"""
    off = OfflineFeatureEvaluator(evaluate)
    on = OnlineFeatureEvaluator(evaluate)
    a = off.evaluate_rows(offline_rows)
    b = on.evaluate_rows(online_rows if online_rows is not None else offline_rows)
    common = sorted(set(a) & set(b))
    max_abs = 0.0
    max_rel = 0.0
    first = ""
    for key in common:
        d = abs(a[key] - b[key])
        rd = d / max(abs(a[key]), 1e-12)
        if d > max_abs:
            max_abs = d
        if rd > max_rel:
            max_rel = rd
        if (d > abs_tol and rd > rel_tol) and not first:
            first = f"{key[0]}|{key[1]}"
    only_a = len(set(a) - set(b))
    only_b = len(set(b) - set(a))
    passed = not first and only_a == 0 and only_b == 0
    if not a and not b:
        passed = True
    return FeatureParityReport(
        n_compared=len(common),
        max_abs_diff=max_abs,
        max_rel_diff=max_rel,
        passed=passed,
        abs_tol=abs_tol,
        rel_tol=rel_tol,
        first_divergence=first,
        details={"n_only_offline": only_a, "n_only_online": only_b},
    )


def _row_key(r: Mapping[str, Any]) -> tuple[str, str] | None:
    dt = str(r.get("trading_date") or r.get("datetime") or "")[:10]
    inst = str(r.get("instrument_key") or r.get("instrument") or "")
    if not dt or not inst:
        return None
    return dt, inst
