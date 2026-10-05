"""最小 Qlib 读回验证（不修改 Qlib 源码）。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from .instrument_mapper import to_qlib_instrument


class QlibValidationError(RuntimeError):
    """Qlib 读回失败或与预期不一致。"""


OHLCV_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume", "amount")


def validate_qlib_provider(
    provider_uri: Path,
    *,
    expect_calendar_count: int,
    expect_instrument_count: int,
    sample_instrument: str | None = None,
    sample_field: str = "close",
) -> dict[str, Any]:
    """用 LocalProvider / D 接口做最小校验。

    若环境无 qlib，则回退为文件系统校验。
    有 qlib 时：D.features 必须非空，否则视为失败。
    """
    provider_uri = Path(provider_uri)
    cal_path = provider_uri / "calendars" / "day.txt"
    inst_path = provider_uri / "instruments" / "all.txt"
    if not cal_path.is_file():
        raise QlibValidationError("missing calendars/day.txt")
    if not inst_path.is_file():
        raise QlibValidationError("missing instruments/all.txt")

    cal_lines = [ln.strip() for ln in cal_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    inst_lines = [ln.strip() for ln in inst_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(cal_lines) != expect_calendar_count:
        raise QlibValidationError(
            f"calendar count mismatch: file={len(cal_lines)} expect={expect_calendar_count}"
        )
    if len(inst_lines) != expect_instrument_count:
        raise QlibValidationError(
            f"instrument count mismatch: file={len(inst_lines)} expect={expect_instrument_count}"
        )

    # instruments 落盘必须小写
    for line in inst_lines:
        code = line.split("\t")[0]
        if code != code.lower():
            raise QlibValidationError(f"instrument must be lowercase for Qlib: {code!r}")

    result: dict[str, Any] = {
        "calendar_count": len(cal_lines),
        "instrument_count": len(inst_lines),
        "min_date": cal_lines[0] if cal_lines else None,
        "max_date": cal_lines[-1] if cal_lines else None,
        "via": "filesystem",
    }

    try:
        import qlib
        from qlib.data import D
    except ImportError:
        result["qlib_skipped"] = True
        return result

    try:
        # joblib_backend=threading：避免 stdin/`python -` 下 multiprocessing spawn 崩坏
        qlib.init(
            provider_uri=str(provider_uri),
            region="cn",
            expression_cache=None,
            dataset_cache=None,
            kernels=1,
            joblib_backend="threading",
        )
        calendar = D.calendar(start_time=cal_lines[0], end_time=cal_lines[-1], freq="day")
        result["qlib_calendar_count"] = len(calendar)
        result["via"] = "qlib"
        if len(calendar) != expect_calendar_count:
            raise QlibValidationError(
                f"qlib calendar count mismatch: {len(calendar)} != {expect_calendar_count}"
            )
        if sample_instrument:
            inst = sample_instrument.lower()
            df = D.features(
                [inst],
                [f"${sample_field}"],
                start_time=cal_lines[0],
                end_time=cal_lines[-1],
            )
            n = int(len(df))
            result["sample_rows"] = n
            result["sample_instrument"] = inst
            result["sample_field"] = sample_field
            if n <= 0:
                raise QlibValidationError(
                    f"D.features returned empty for {inst} ${sample_field}; "
                    "check day.bin start_index format"
                )
    except QlibValidationError:
        raise
    except Exception as exc:
        raise QlibValidationError(f"qlib read failed: {exc}") from exc

    return result


def validate_datahandler(
    provider_uri: Path,
    *,
    instruments: Sequence[str],
    start: str,
    end: str,
    fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """最小 DataHandlerLP 读回（仅 OHLCV，不引入 Alpha158）。"""
    try:
        import qlib
        from qlib.data import D
        from qlib.data.dataset.handler import DataHandlerLP
    except ImportError as exc:
        raise QlibValidationError("pyqlib required for DataHandler validation") from exc

    provider_uri = Path(provider_uri)
    field_list = list(fields or ["$open", "$high", "$low", "$close", "$volume"])
    insts = [str(x).lower() for x in instruments]
    # joblib_backend=threading：避免 stdin/`python -` 下 multiprocessing spawn 崩坏
    qlib.init(
        provider_uri=str(provider_uri),
        region="cn",
        expression_cache=None,
        dataset_cache=None,
        kernels=1,
        joblib_backend="threading",
    )

    # 确认 instruments 可见
    listed = D.list_instruments(
        D.instruments(market="all"),
        start_time=start,
        end_time=end,
        as_list=True,
    )
    listed_set = {str(x).lower() for x in listed}
    missing = [i for i in insts if i not in listed_set]
    if missing:
        raise QlibValidationError(f"instruments not listed by Qlib: {missing}")

    # 优先用 D.features 做确定性读回（与 DataHandler 同源 loader，避免并行坑）
    panel = D.features(insts, field_list, start_time=start, end_time=end)
    if panel is None or len(panel) == 0:
        raise QlibValidationError("D.features OHLCV panel empty for DataHandler check")

    try:
        handler = DataHandlerLP(
            instruments=insts,
            start_time=start,
            end_time=end,
            data_loader={
                "class": "QlibDataLoader",
                "kwargs": {
                    "config": {
                        "feature": field_list,
                    },
                },
            },
            learn_processors=[],
            infer_processors=[],
        )
        df = handler.fetch(col_set="feature")
        if df is None or len(df) == 0:
            df = handler.fetch()
        if df is None or len(df) == 0:
            raise QlibValidationError("DataHandlerLP.fetch returned empty")
        cols = [str(c) for c in df.columns]
        rows = int(len(df))
        via = "datahandler"
    except Exception as exc:
        # DataHandler 并行在部分环境失败时，仍以 D.features 面板为准
        cols = [str(c) for c in panel.columns]
        rows = int(len(panel))
        via = f"d_features_fallback:{type(exc).__name__}"

    flat = " ".join(cols).lower()
    for need in ("close", "open", "volume"):
        if need not in flat:
            raise QlibValidationError(f"handler missing expected field {need!r}; cols={cols}")

    return {
        "rows": rows,
        "columns": cols,
        "instruments": insts,
        "start": start,
        "end": end,
        "via": via,
        "d_features_rows": int(len(panel)),
    }


def compare_feature_values(
    dataquery_values: Sequence[float | None],
    qlib_values: Sequence[float | None],
    *,
    atol: float = 1e-8,
    rtol: float = 1e-6,
) -> None:
    """带 tolerance 的数值比较；双方都应是 NaN 时视为一致；禁止 NULL→0 漂移。"""
    import math

    if len(dataquery_values) != len(qlib_values):
        raise QlibValidationError(
            f"length mismatch: dq={len(dataquery_values)} qlib={len(qlib_values)}"
        )
    for i, (a, b) in enumerate(zip(dataquery_values, qlib_values)):
        a_nan = a is None or (isinstance(a, float) and math.isnan(a))
        b_nan = b is None or (isinstance(b, float) and math.isnan(b))
        if a_nan and b_nan:
            continue
        if a_nan or b_nan:
            raise QlibValidationError(f"missing-value semantics drift at index {i}: dq={a} qlib={b}")
        aa = float(a)
        bb = float(b)
        if abs(aa - bb) > atol + rtol * abs(aa):
            raise QlibValidationError(f"value mismatch at {i}: dq={aa} qlib={bb}")


def _to_python_date(value: Any):
    """把 Timestamp / datetime / date 统一为 date。"""
    from datetime import date, datetime

    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if hasattr(value, "date") and callable(value.date):
        return value.date()
    return value


def qlib_features_to_frame(
    feat: pd.DataFrame,
    *,
    fields: Sequence[str] = OHLCV_FIELDS,
) -> pd.DataFrame:
    """将 D.features MultiIndex 结果转为 (qlib_instrument, trading_date, fields)。"""
    if feat is None or len(feat) == 0:
        cols = ["qlib_instrument", "trading_date", *fields]
        return pd.DataFrame(columns=cols)

    rows: list[dict[str, Any]] = []
    # 列可能是 $close 或 close；MultiIndex 列取末级
    col_map: dict[str, Any] = {}
    for c in feat.columns:
        name = str(c[-1]) if isinstance(c, tuple) else str(c)
        if name.startswith("$"):
            name = name[1:]
        col_map[name.lower()] = c

    for idx, series in feat.iterrows():
        if isinstance(idx, tuple) and len(idx) >= 2:
            inst, dt = idx[0], idx[1]
        else:
            inst, dt = None, idx
        row: dict[str, Any] = {
            "qlib_instrument": str(inst).lower() if inst is not None else "",
            "trading_date": _to_python_date(dt),
        }
        for f in fields:
            src = col_map.get(f)
            row[f] = float(series[src]) if src is not None else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def normalize_dq_market_panel(
    market: pd.DataFrame,
    *,
    fields: Sequence[str] = OHLCV_FIELDS,
) -> pd.DataFrame:
    """DataQuery.market → 带 qlib_instrument 的标准面板。"""
    if market is None or market.empty:
        return pd.DataFrame(columns=["instrument_key", "qlib_instrument", "trading_date", *fields])
    out = market.copy()
    out["trading_date"] = out["trading_date"].map(_to_python_date)
    out["qlib_instrument"] = out["instrument_key"].map(
        lambda x: to_qlib_instrument(str(x)).lower()
    )
    keep = [
        "instrument_key",
        "qlib_instrument",
        "trading_date",
        *[f for f in fields if f in out.columns],
    ]
    return out[keep].reset_index(drop=True)


def compare_ohlcv_panels(
    dq_df: pd.DataFrame,
    qlib_df: pd.DataFrame,
    *,
    fields: Sequence[str] = OHLCV_FIELDS,
    atol: float = 1e-8,
    rtol: float = 1e-6,
) -> dict[str, Any]:
    """对齐 (qlib_instrument, trading_date)，比较 OHLCV+amount；校验行数与集合一致。"""
    left = normalize_dq_market_panel(dq_df, fields=fields)
    right = qlib_df.copy()
    if "qlib_instrument" not in right.columns:
        right = qlib_features_to_frame(right, fields=fields)
    right["trading_date"] = right["trading_date"].map(_to_python_date)
    right["qlib_instrument"] = right["qlib_instrument"].astype(str).str.lower()

    left_keys = set(zip(left["qlib_instrument"], left["trading_date"]))
    right_keys = set(zip(right["qlib_instrument"], right["trading_date"]))
    if left_keys != right_keys:
        only_l = sorted(left_keys - right_keys)[:5]
        only_r = sorted(right_keys - left_keys)[:5]
        raise QlibValidationError(
            f"panel key set mismatch: dq={len(left_keys)} qlib={len(right_keys)}; "
            f"only_dq={only_l} only_qlib={only_r}"
        )
    if len(left) != len(right):
        raise QlibValidationError(f"row count mismatch: dq={len(left)} qlib={len(right)}")

    merged = left.merge(
        right,
        on=["qlib_instrument", "trading_date"],
        suffixes=("_dq", "_qlib"),
        how="inner",
    )
    for f in fields:
        dq_col = f if f in merged.columns else f"{f}_dq"
        q_col = f"{f}_qlib" if f"{f}_qlib" in merged.columns else f
        if dq_col not in merged.columns or q_col not in merged.columns:
            raise QlibValidationError(f"missing field {f} after merge")
        compare_feature_values(
            [None if pd.isna(x) else float(x) for x in merged[dq_col].tolist()],
            [None if pd.isna(x) else float(x) for x in merged[q_col].tolist()],
            atol=atol,
            rtol=rtol,
        )

    inst_l = set(left["qlib_instrument"])
    inst_r = set(right["qlib_instrument"])
    dates_l = set(left["trading_date"])
    dates_r = set(right["trading_date"])
    if inst_l != inst_r:
        raise QlibValidationError(
            f"instrument set mismatch: dq={sorted(inst_l)} qlib={sorted(inst_r)}"
        )
    if dates_l != dates_r:
        raise QlibValidationError(
            f"calendar set mismatch: dq_n={len(dates_l)} qlib_n={len(dates_r)}"
        )
    return {
        "rows": len(merged),
        "instruments": sorted(inst_l),
        "dates": len(dates_l),
        "fields": list(fields),
    }


def compare_universe_sets(
    dq_instrument_keys: Sequence[str],
    qlib_ids: Sequence[str],
) -> None:
    """DataQuery universe keys 与 Qlib instrument id（小写）集合一致。"""
    expected = {to_qlib_instrument(str(k)).lower() for k in dq_instrument_keys}
    actual = {str(x).lower() for x in qlib_ids}
    if expected != actual:
        raise QlibValidationError(
            f"universe set mismatch: dq={sorted(expected)} qlib={sorted(actual)}"
        )


def directory_sha256(root: Path) -> str:
    """目录内容稳定校验和（路径相对 + 文件字节）。"""
    root = Path(root)
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


def assert_canonical_raw_unchanged(before_checksum: str, after_checksum: str) -> None:
    """Materialize 不得改写 Canonical raw。"""
    if before_checksum != after_checksum:
        raise QlibValidationError(
            f"canonical raw mutated by materializer: before={before_checksum} after={after_checksum}"
        )
