"""存储层全局配置：本地路径约定 + Cloudflare R2 / 百度网盘配置读取。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 本包在 app/services/level2_ingest，上溯三级是 backend_api_python。
ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

# 入库目标与回测读取后端（互斥切换：r2 | baidu）
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "r2").strip().lower()
STORAGE_READ = os.getenv("STORAGE_READ", "r2").strip().lower()

R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "level2")
R2_PREFIX = os.getenv("R2_PREFIX", "l2")
# 日频因子和原始明细分开。图表按 l2_factors/{年}/{年月}/{YYYYMMDD}.parquet 读取。
R2_FACTOR_PREFIX = os.getenv("R2_FACTOR_PREFIX", "l2_factors").strip().strip("/") or "l2_factors"

# 百度网盘开放平台（OAuth + 应用目录 /apps/{BAIDU_APP_NAME}/）
BAIDU_APP_KEY = os.getenv("BAIDU_APP_KEY", "")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")
BAIDU_APP_NAME = os.getenv("BAIDU_APP_NAME", "level2")
BAIDU_REMOTE_PREFIX = os.getenv("BAIDU_REMOTE_PREFIX", R2_PREFIX)
BAIDU_ACCESS_TOKEN = os.getenv("BAIDU_ACCESS_TOKEN", "")
BAIDU_REFRESH_TOKEN = os.getenv("BAIDU_REFRESH_TOKEN", "")
BAIDU_REDIRECT_URI = os.getenv("BAIDU_REDIRECT_URI", "https://www.ivip.site/")
BAIDU_UPLOAD_WORKERS = max(1, int(os.getenv("BAIDU_UPLOAD_WORKERS", "4")))

# 入库并发：local 可高并发叠满 RTT；7z solid 归档并发解压会互相拖慢，默认更低
INGEST_WORKERS = max(1, int(os.getenv("INGEST_WORKERS", "15")))
INGEST_7Z_WORKERS = max(1, int(os.getenv("INGEST_7Z_WORKERS", "4")))

# 归档与转换产物放在 backend data 下，和图表临时明细 level2_parquet 分开。
DATA_ROOT = Path(os.getenv("LEVEL2_RAW_DIR", str(ROOT / "data" / "level2_raw")))
STAGING_ROOT = Path(os.getenv("LEVEL2_STAGING_DIR", str(ROOT / "data" / "level2_staging")))
STAGING_PARQUET = STAGING_ROOT / "parquet"
MANIFEST_DIR = STAGING_ROOT / "manifests"
CATALOG_DIR = STAGING_ROOT / "catalogs"
FAILURE_DIR = STAGING_ROOT / "failures"

FILE_TYPES = ("逐笔成交", "逐笔委托", "行情")


def market_suffix(code: str) -> str:
    code = code.split(".")[0]
    return ".SH" if code[0] in "69" else ".SZ"


def object_key(date: str, code: str, ftype: str) -> str:
    """逻辑对象键（R2 与百度共用，不含后端前缀）。"""
    return f"{R2_PREFIX}/{date}/{code}/{ftype}.parquet"


def r2_key(date: str, code: str, ftype: str) -> str:
    """兼容旧名：与 object_key 相同。"""
    return object_key(date, code, ftype)


def factor_object_key(date: str) -> str:
    """日频因子在 R2 上的键：``l2_factors/{年}/{年月}/{YYYYMMDD}.parquet``。"""
    day = str(date).strip()
    return f"{R2_FACTOR_PREFIX}/{day[:4]}/{day[:6]}/{day}.parquet"


def manifest_object_key(date: str) -> str:
    return f"{R2_PREFIX}/_manifests/{date}.parquet"


def manifest_r2_key(date: str) -> str:
    return manifest_object_key(date)


def catalog_object_key(date: str, backend: str | None = None) -> str:
    """远程 catalog 键：按后端分目录，R2/百度进度互不影响。"""
    b = (backend or STORAGE_BACKEND).strip().lower()
    return f"{R2_PREFIX}/_catalog/{b}/{date}.parquet"


def catalog_r2_key(date: str, backend: str | None = None) -> str:
    return catalog_object_key(date, backend=backend or "r2")


def baidu_apps_root() -> str:
    """百度应用根目录，上传 API 要求路径位于 /apps/ 下。"""
    return f"/apps/{BAIDU_APP_NAME}"


def date_hierarchy(date: str) -> str:
    """交易日 → 年/年月/年月日，如 20260506 → 2026/202605/20260506。"""
    d = date.strip()
    if len(d) != 8 or not d.isdigit():
        raise ValueError(f"日期须为 YYYYMMDD，收到: {date!r}")
    return f"{d[:4]}/{d[:6]}/{d}"


def logical_key_to_baidu_rel(logical_key: str) -> str:
    """逻辑键 → 百度相对路径（apps 根下）。

    数据键 `{prefix}/{YYYYMMDD}/...` 插入年/年月；
    `_catalog` / `_manifests` 等以下划线段开头的路径原样保留。
    """
    key = logical_key.lstrip("/")
    parts = key.split("/")
    # 期望：prefix / YYYYMMDD / ...
    if len(parts) >= 2 and len(parts[1]) == 8 and parts[1].isdigit():
        date = parts[1]
        rest = "/".join(parts[2:])
        nested = f"{parts[0]}/{date_hierarchy(date)}"
        return f"{nested}/{rest}" if rest else nested
    return key


def baidu_rel_to_logical_key(rel: str) -> str:
    """百度相对路径 → 逻辑键（去掉年/年月层）。

    识别 `{prefix}/{YYYY}/{YYYYMM}/{YYYYMMDD}/...`；其它路径原样返回。
    """
    key = rel.lstrip("/")
    parts = key.split("/")
    # 期望：prefix / year / yyyymm / yyyymmdd / ...
    if (
        len(parts) >= 4
        and len(parts[1]) == 4
        and parts[1].isdigit()
        and len(parts[2]) == 6
        and parts[2].isdigit()
        and len(parts[3]) == 8
        and parts[3].isdigit()
        and parts[3].startswith(parts[2])
        and parts[2].startswith(parts[1])
    ):
        date = parts[3]
        rest = "/".join(parts[4:])
        flat = f"{parts[0]}/{date}"
        return f"{flat}/{rest}" if rest else flat
    return key


def baidu_path(date: str, code: str, ftype: str) -> str:
    """百度绝对路径：/apps/{app}/{prefix}/{年}/{年月}/{日}/{code}/{ftype}.parquet"""
    return baidu_path_from_key(object_key(date, code, ftype))


def baidu_path_from_key(logical_key: str) -> str:
    """逻辑键 → 百度绝对路径（数据键自动插入年/年月层级）。"""
    rel = logical_key_to_baidu_rel(logical_key)
    return f"{baidu_apps_root()}/{rel}"


def ingest_workers() -> int:
    """local 入库并发：百度后端时使用较低上传并发。"""
    if STORAGE_BACKEND == "baidu":
        return BAIDU_UPLOAD_WORKERS
    return INGEST_WORKERS


def ingest_7z_workers() -> int:
    """7z 流式入库并发：百度后端时使用较低上传并发。"""
    if STORAGE_BACKEND == "baidu":
        return BAIDU_UPLOAD_WORKERS
    return INGEST_7Z_WORKERS


def local_csv_path(date: str, code: str, ftype: str) -> Path:
    return DATA_ROOT / date / code / f"{ftype}.csv"


def local_parquet_path(date: str, code: str, ftype: str) -> Path:
    return STAGING_PARQUET / date / code / f"{ftype}.parquet"


def local_manifest_path(date: str) -> Path:
    return MANIFEST_DIR / f"{date}.parquet"


def local_catalog_path(date: str, backend: str | None = None) -> Path:
    """本地 catalog：.staging/catalogs/{backend}/{date}.parquet"""
    b = (backend or STORAGE_BACKEND).strip().lower()
    return CATALOG_DIR / b / f"{date}.parquet"
