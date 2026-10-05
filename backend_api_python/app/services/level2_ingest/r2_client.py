"""Cloudflare R2（S3 兼容 API）客户端封装。

boto3 在真正建连时再导入，路径和键的单测不必安装这个包。
"""
from __future__ import annotations

from . import config

_client = None
# 当前单例连接池容量；并发入库前可按 workers 放大并重建
_pool_connections = 0


def is_configured() -> bool:
    """凭证预检：endpoint 与 access key 均已配置才可安全调用 R2。"""
    return bool(config.R2_ENDPOINT_URL and config.R2_ACCESS_KEY_ID and config.R2_SECRET_ACCESS_KEY)


def configure_pool(min_connections: int) -> None:
    """保证 boto3 连接池不少于 min_connections，避免 ThreadPool 打满后排队。

    若已有 client 且池更小，则丢弃重建（下次 get_client 生效）。
    """
    global _client, _pool_connections
    need = max(10, int(min_connections))
    if _client is not None and _pool_connections >= need:
        return
    _client = None
    _pool_connections = need


def get_client():
    global _client, _pool_connections
    if _client is None:
        # 未显式 configure 时按 local 并发预留连接，避免默认 10 成为瓶颈
        if _pool_connections < 10:
            _pool_connections = max(
                10,
                config.INGEST_WORKERS + 8,
                config.INGEST_7Z_WORKERS + 8,
            )
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=config.R2_ENDPOINT_URL,
            aws_access_key_id=config.R2_ACCESS_KEY_ID,
            aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(max_pool_connections=_pool_connections),
        )
    return _client


def exists(key: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        get_client().head_object(Bucket=config.R2_BUCKET, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def list_keys(prefix: str) -> list[str]:
    """批量列举 prefix 下对象键（用于 catalog 同步，替代逐文件 HEAD）。"""
    if not config.R2_ENDPOINT_URL:
        return []
    client = get_client()
    keys: list[str] = []
    token = None
    while True:
        kwargs = {"Bucket": config.R2_BUCKET, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            keys.append(obj["Key"])
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return keys


def upload_bytes(key: str, data: bytes) -> str:
    """上传字节到 R2，返回 ETag（去引号）。"""
    resp = get_client().put_object(Bucket=config.R2_BUCKET, Key=key, Body=data)
    return str(resp.get("ETag", "")).strip('"')


def download_bytes(key: str) -> bytes:
    obj = get_client().get_object(Bucket=config.R2_BUCKET, Key=key)
    return obj["Body"].read()
