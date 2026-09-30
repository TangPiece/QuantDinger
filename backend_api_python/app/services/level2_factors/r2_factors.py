"""把日频因子 Parquet 同步到 Cloudflare R2。

对象键是 ``l2_factors/{YYYY}/{YYYYMM}/{YYYYMMDD}.parquet``，和原始明细的 ``l2/`` 分开。
旧的扁平键 ``l2_factors/{YYYYMMDD}.parquet`` 只用于下载回退。
凭证没配齐时上传和下载都跳过，图表仍只用本地文件。测试可注入替身，不连网。
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable

_log = logging.getLogger(__name__)
_uploader: Callable[[str, bytes], None] | None = None
_downloader: Callable[[str], bytes | None] | None = None
_client = None


def set_factor_remote(
    uploader: Callable[[str, bytes], None] | None,
    downloader: Callable[[str], bytes | None] | None,
) -> None:
    """测试注入。``downloader`` 没有对象时返回 None。"""
    global _uploader, _downloader
    _uploader = uploader
    _downloader = downloader


def factor_prefix() -> str:
    """因子对象的目录前缀，不含日期文件名。"""
    return os.getenv("R2_FACTOR_PREFIX", "l2_factors").strip().strip("/") or "l2_factors"


def factor_object_key(date: str) -> str:
    """某日因子文件在 R2 上的键，按年、年月分层，方便在桶里浏览。"""
    day = str(date).strip()
    return f"{factor_prefix()}/{day[:4]}/{day[:6]}/{day}.parquet"


def symbol_object_key(symbol: str) -> str:
    """一只股票全部历史基础因子的键。读取个股序列用，不替代按日宽表。"""
    from app.services.level2_factor_panel import canonical_symbol

    code = canonical_symbol(symbol)
    return f"{factor_prefix()}/symbol/{code}.parquet"


def _legacy_factor_object_key(date: str) -> str:
    """改分层之前的对象键。只在新键不存在时读取。"""
    return f"{factor_prefix()}/{str(date).strip()}.parquet"


def upload_symbol_file(symbol: str, payload: bytes) -> None:
    """上传一只股票的因子文件。没配凭证时抛出，避免按周任务把失败算成成功。"""
    if not _configured():
        raise RuntimeError("R2 未配置")
    _client_instance().put_object(Bucket=_bucket(), Key=symbol_object_key(symbol), Body=payload)


def download_symbol_file(symbol: str) -> bytes | None:
    """下载一只股票的因子文件。没有该对象或没配凭证时返回 None。"""
    if not _configured():
        return None
    return _get_object(str(symbol), symbol_object_key(symbol))


def upload_factor_file(date: str, payload: bytes) -> None:
    """上传一天的因子文件。没配凭证时什么都不做。"""
    if _uploader is not None:
        _uploader(date, payload)
        return
    if not _configured():
        return
    try:
        _client_instance().put_object(Bucket=_bucket(), Key=factor_object_key(date), Body=payload)
    except Exception:
        _log.warning("Level2 因子上传 R2 失败 %s", date, exc_info=True)


def list_factor_dates() -> list[str]:
    """列出 R2 上已有的因子交易日。没配凭证时返回空列表。"""
    if not _configured() or _downloader is not None:
        # 测试注入了按日下载时，不扫描远程桶。
        return []
    try:
        client = _client_instance()
        prefix = f"{factor_prefix()}/"
        dates: list[str] = []
        token = None
        while True:
            kwargs: dict = {"Bucket": _bucket(), "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or []:
                name = str(item.get("Key") or "").rsplit("/", 1)[-1]
                stem = name[:-8] if name.endswith(".parquet") else ""
                if len(stem) == 8 and stem.isdigit():
                    dates.append(stem)
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        return sorted(set(dates))
    except Exception:
        _log.warning("Level2 因子列举 R2 失败", exc_info=True)
        return []


def download_factor_file(date: str) -> bytes | None:
    """下载一天的因子文件。没有该对象或没配凭证时返回 None。

    先读年月路径，没有再读改分层之前的扁平路径。
    """
    if _downloader is not None:
        return _downloader(date)
    if not _configured():
        return None
    for key in (factor_object_key(date), _legacy_factor_object_key(date)):
        payload = _get_object(date, key)
        if payload is not None:
            return payload
    return None


def _get_object(date: str, key: str) -> bytes | None:
    """读取一个对象。不存在返回 None；其它错误记日志后也当作没有。"""
    try:
        response = _client_instance().get_object(Bucket=_bucket(), Key=key)
        return response["Body"].read()
    except Exception as exc:
        response = getattr(exc, "response", None)
        error_code = ""
        if isinstance(response, dict):
            error_code = str((response.get("Error") or {}).get("Code") or "")
        if error_code not in {"404", "NoSuchKey", "NotFound"}:
            _log.warning("Level2 因子读取 R2 失败 %s %s", date, key, exc_info=True)
        return None


def _configured() -> bool:
    return bool(
        os.getenv("R2_ENDPOINT_URL", "").strip()
        and os.getenv("R2_ACCESS_KEY_ID", "").strip()
        and os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    )


def _bucket() -> str:
    return os.getenv("R2_BUCKET", "level2").strip() or "level2"


def _client_instance():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT_URL", "").strip(),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID", "").strip(),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
            region_name="auto",
            config=Config(max_pool_connections=16),
        )
    return _client
