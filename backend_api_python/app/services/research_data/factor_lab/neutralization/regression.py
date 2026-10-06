"""横截面 OLS Neutralizer：neutralized = residual（FULL）。"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any, Optional

import numpy as np

from .exposure import ExposureProvider
from .protocol import (
    DayStatus,
    ExposureDiagnostic,
    ExposureRow,
    NeutralizationSpec,
    NeutralizedFactorRow,
)


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = dx2 = dy2 = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        num += dx * dy
        dx2 += dx * dx
        dy2 += dy * dy
    if dx2 <= 0.0 or dy2 <= 0.0:
        return None
    return num / math.sqrt(dx2 * dy2)


def _rank(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    return _pearson(_rank(xs), _rank(ys))


class RegressionNeutralizer:
    """逐日横截面 OLS；Industry 用 one-hot（drop_first）。"""

    def neutralize(
        self,
        factor_rows: list[dict[str, Any]],
        provider: ExposureProvider,
        spec: NeutralizationSpec,
    ) -> tuple[list[NeutralizedFactorRow], list[ExposureRow], list[ExposureDiagnostic]]:
        """返回 neutralized 行、用到的暴露、按日诊断。"""
        by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for r in factor_rows:
            d = r.get("trading_date") or r.get("factor_date")
            if isinstance(d, str):
                d = date.fromisoformat(d[:10])
            elif hasattr(d, "date") and not isinstance(d, date):
                d = d.date()
            by_date[d].append(r)  # type: ignore[index]

        out_rows: list[NeutralizedFactorRow] = []
        all_exp: list[ExposureRow] = []
        diags: list[ExposureDiagnostic] = []
        min_n = int(spec.min_cross_section_size)
        need_industry = "INDUSTRY" in spec.targets
        need_size = "SIZE" in spec.targets
        need_beta = "BETA" in spec.targets

        for d in sorted(by_date):
            day = by_date[d]
            keys = [str(r["instrument_key"]) for r in day]
            exps = provider.load_for_date(d, keys, spec)
            all_exp.extend(exps)
            exp_map: dict[str, dict[str, float]] = defaultdict(dict)
            industry_label: dict[str, str] = {}
            for e in exps:
                if e.exposure_code.startswith("INDUSTRY"):
                    # INDUSTRY:<code> 或 INDUSTRY 数值 + 标签在 code 后缀
                    label = e.exposure_code
                    if e.exposure_code == "INDUSTRY":
                        label = f"INDUSTRY:{int(e.exposure_value)}"
                    industry_label[e.instrument_key] = label
                    exp_map[e.instrument_key]["INDUSTRY_FLAG"] = 1.0
                else:
                    exp_map[e.instrument_key][e.exposure_code] = float(
                        e.exposure_value
                    )

            # 组装回归样本
            y_list: list[float] = []
            iks: list[str] = []
            size_vals: list[float] = []
            beta_vals: list[float] = []
            ind_labs: list[str] = []
            raw_by_ik: dict[str, float] = {}
            for r in day:
                ik = str(r["instrument_key"])
                fv = r.get("value", r.get("factor_value", r.get("raw_factor")))
                if fv is None:
                    continue
                try:
                    yv = float(fv)
                except (TypeError, ValueError):
                    continue
                if math.isnan(yv) or math.isinf(yv):
                    continue
                em = exp_map.get(ik, {})
                if need_size and "SIZE" not in em:
                    continue
                if need_beta and "BETA" not in em:
                    continue
                if need_industry and ik not in industry_label:
                    continue
                y_list.append(yv)
                iks.append(ik)
                raw_by_ik[ik] = yv
                size_vals.append(em.get("SIZE", 0.0))
                beta_vals.append(em.get("BETA", 0.0))
                ind_labs.append(industry_label.get(ik, "INDUSTRY:UNK"))

            n = len(y_list)
            if n < min_n:
                for r in day:
                    ik = str(r["instrument_key"])
                    fv = r.get("value", r.get("factor_value", r.get("raw_factor")))
                    try:
                        raw = float(fv) if fv is not None else float("nan")
                    except (TypeError, ValueError):
                        continue
                    out_rows.append(
                        NeutralizedFactorRow(
                            instrument_key=ik,
                            trading_date=d,
                            raw_factor=raw,
                            neutralized_factor=None,
                            status="INSUFFICIENT",
                        )
                    )
                diags.append(
                    ExposureDiagnostic(
                        trading_date=d,
                        exposure_code="MODEL",
                        sample_count=n,
                        status="INSUFFICIENT",
                    )
                )
                continue

            # 构建设计矩阵
            cols: list[np.ndarray] = []
            col_names: list[str] = []
            if spec.include_intercept:
                cols.append(np.ones(n))
                col_names.append("INTERCEPT")
            if need_size:
                arr = np.asarray(size_vals, dtype=float)
                if float(np.nanstd(arr)) == 0.0:
                    for ik, raw in raw_by_ik.items():
                        out_rows.append(
                            NeutralizedFactorRow(
                                instrument_key=ik,
                                trading_date=d,
                                raw_factor=raw,
                                neutralized_factor=None,
                                status="CONSTANT",
                            )
                        )
                    diags.append(
                        ExposureDiagnostic(
                            trading_date=d,
                            exposure_code="SIZE",
                            sample_count=n,
                            status="CONSTANT",
                        )
                    )
                    continue
                cols.append(arr)
                col_names.append("SIZE")
            if need_beta:
                cols.append(np.asarray(beta_vals, dtype=float))
                col_names.append("BETA")
            if need_industry:
                levels = sorted(set(ind_labs))
                if len(levels) < 2:
                    for ik, raw in raw_by_ik.items():
                        out_rows.append(
                            NeutralizedFactorRow(
                                instrument_key=ik,
                                trading_date=d,
                                raw_factor=raw,
                                neutralized_factor=None,
                                status="CONSTANT",
                            )
                        )
                    diags.append(
                        ExposureDiagnostic(
                            trading_date=d,
                            exposure_code="INDUSTRY",
                            sample_count=n,
                            status="CONSTANT",
                        )
                    )
                    continue
                # drop_first
                for lab in levels[1:]:
                    cols.append(
                        np.asarray(
                            [1.0 if x == lab else 0.0 for x in ind_labs],
                            dtype=float,
                        )
                    )
                    col_names.append(lab)

            X = np.column_stack(cols)
            y = np.asarray(y_list, dtype=float)
            # 秩检查
            rank = int(np.linalg.matrix_rank(X))
            if rank < X.shape[1]:
                for ik, raw in raw_by_ik.items():
                    out_rows.append(
                        NeutralizedFactorRow(
                            instrument_key=ik,
                            trading_date=d,
                            raw_factor=raw,
                            neutralized_factor=None,
                            status="SINGULAR",
                        )
                    )
                diags.append(
                    ExposureDiagnostic(
                        trading_date=d,
                        exposure_code="MODEL",
                        sample_count=n,
                        status="SINGULAR",
                    )
                )
                continue

            beta_hat, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            y_hat = X @ beta_hat
            resid = y - y_hat
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            ss_res = float(np.sum(resid**2))
            r2 = None if ss_tot <= 0 else 1.0 - ss_res / ss_tot

            neu_map = {ik: float(resid[i]) for i, ik in enumerate(iks)}
            for r in day:
                ik = str(r["instrument_key"])
                fv = r.get("value", r.get("factor_value", r.get("raw_factor")))
                try:
                    raw = float(fv) if fv is not None else float("nan")
                except (TypeError, ValueError):
                    continue
                out_rows.append(
                    NeutralizedFactorRow(
                        instrument_key=ik,
                        trading_date=d,
                        raw_factor=raw,
                        neutralized_factor=neu_map.get(ik),
                        status="OK" if ik in neu_map else "MISSING",
                    )
                )

            # Diagnostics：SIZE / BETA / INDUSTRY 综合
            for code, vals in (("SIZE", size_vals), ("BETA", beta_vals)):
                if code == "SIZE" and not need_size:
                    continue
                if code == "BETA" and not need_beta:
                    continue
                before = _pearson(y_list, vals)
                after_vals = [
                    vals[i] for i, ik in enumerate(iks) if ik in neu_map
                ]
                after_neu = [neu_map[ik] for ik in iks if ik in neu_map]
                after = _pearson(after_neu, after_vals) if after_neu else None
                diags.append(
                    ExposureDiagnostic(
                        trading_date=d,
                        exposure_code=code,
                        correlation_before=before,
                        correlation_after=after,
                        spearman_before=_spearman(y_list, vals),
                        spearman_after=_spearman(after_neu, after_vals)
                        if after_neu
                        else None,
                        r_squared=r2,
                        sample_count=n,
                        status="OK",
                    )
                )
            if need_industry:
                # 用行业标签秩作 proxy：编码为 category index
                ind_num = [
                    float(sorted(set(ind_labs)).index(x)) for x in ind_labs
                ]
                before = _pearson(y_list, ind_num)
                after_neu = [neu_map[ik] for ik in iks]
                after = _pearson(after_neu, ind_num)
                diags.append(
                    ExposureDiagnostic(
                        trading_date=d,
                        exposure_code="INDUSTRY",
                        correlation_before=before,
                        correlation_after=after,
                        spearman_before=_spearman(y_list, ind_num),
                        spearman_after=_spearman(after_neu, ind_num),
                        r_squared=r2,
                        sample_count=n,
                        status="OK",
                    )
                )
            diags.append(
                ExposureDiagnostic(
                    trading_date=d,
                    exposure_code="MODEL",
                    r_squared=r2,
                    sample_count=n,
                    status="OK",
                )
            )

        return out_rows, all_exp, diags
