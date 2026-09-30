"""把本地按日宽表收成每只股票一个 Parquet，再上传到 R2。

按日文件仍是主布局，键保持 ``l2_factors/{年}/{年月}/{YYYYMMDD}.parquet``。
股票文件是 ``l2_factors/symbol/{代码}.parquet``，只含基础列，供指标页和 CTA 读长序列。
周中新交易日不在这里追加；读取时从按日宽表抽出这一只补上。
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import pandas as pd

from app.services.level2_factor_panel import canonical_symbol

from .names import stored_columns
from .r2_factors import symbol_object_key, upload_symbol_file

# 几千只小文件同时上传，池子太大容易把连接打满。
_UPLOAD_WORKERS = 8


def daily_factor_files(factors_dir: Path) -> list[Path]:
    """目录根上的 ``YYYYMMDD.parquet``。``symbol/`` 子目录不算。"""
    root = Path(factors_dir)
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.glob("*.parquet")
        if path.stem.isdigit() and len(path.stem) == 8
    )


def collect_symbol_frames(factors_dir: Path) -> dict[str, pd.DataFrame]:
    """按股票归并基础列。同一交易日重复出现时留下后读到的那一行。"""
    frames: list[pd.DataFrame] = []
    columns = stored_columns()
    for path in daily_factor_files(factors_dir):
        table = pd.read_parquet(path)
        keep = [column for column in columns if column in table.columns]
        if "symbol" not in keep or "trade_date" not in keep:
            continue
        frames.append(table[keep])
    if not frames:
        return {}
    panel = pd.concat(frames, ignore_index=True)
    panel["trade_date"] = panel["trade_date"].astype(str)
    panel["symbol"] = panel["symbol"].map(canonical_symbol)
    panel = panel.drop_duplicates(["symbol", "trade_date"], keep="last")
    grouped: dict[str, pd.DataFrame] = {}
    for symbol, part in panel.groupby("symbol", sort=False):
        grouped[str(symbol)] = part.sort_values("trade_date").reset_index(drop=True)
    return grouped


def rebuild_symbol_mirrors(
    factors_dir: Path,
    *,
    uploader=None,
) -> tuple[int, int]:
    """上传每只股票一份基础因子历史。返回 ``(成功只数, 应上传只数)``。"""
    grouped = collect_symbol_frames(factors_dir)
    if not grouped:
        return 0, 0
    send = uploader or _upload
    workers = min(_UPLOAD_WORKERS, len(grouped))
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_send_one, symbol, frame, send): symbol
            for symbol, frame in grouped.items()
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                future.result()
            except Exception:
                print(f"[symbol] 上传失败 {symbol}", flush=True)
                continue
            done += 1
    return done, len(grouped)


def _send_one(symbol: str, frame: pd.DataFrame, uploader) -> None:
    """一只股票整份上传。调用方保证同一代码不会并发写两次。"""
    buffer = BytesIO()
    columns = [column for column in stored_columns() if column in frame.columns]
    frame[columns].to_parquet(buffer, index=False)
    uploader(symbol_object_key(symbol), buffer.getvalue())


def _upload(key: str, payload: bytes) -> None:
    """从对象键取出代码，走现有 R2 上传。没配凭证时上传函数自己跳过。"""
    code = Path(key).stem
    upload_symbol_file(code, payload)


def main(argv: list[str] | None = None) -> int:
    """从本地按日因子目录重建股票镜像。默认目录是 staging 的 factors。"""
    parser = argparse.ArgumentParser(description="从按日因子文件重建每只股票的 R2 镜像")
    parser.add_argument("--factors-dir", default="", help="YYYYMMDD.parquet 所在目录")
    args = parser.parse_args(argv)
    if args.factors_dir:
        root = Path(args.factors_dir)
    else:
        from app.services.level2_ingest.factor_batch import default_output_dir

        root = default_output_dir()
    done, total = rebuild_symbol_mirrors(root)
    print(f"已上传 {done}/{total} 只股票，目录 {root}", flush=True)
    return 0 if total and done == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
