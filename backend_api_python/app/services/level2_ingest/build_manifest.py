"""一次性为历史 .7z 生成 manifest（以后 pipeline 不再 tar -tf）。"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import config, manifest


def build(date: str, upload: bool = False) -> int:
    seven_z = config.DATA_ROOT / f"{date}.7z"
    if not seven_z.exists():
        raise FileNotFoundError(seven_z)
    print(f"扫描归档（仅此一次）: {seven_z}")
    members = manifest.build_from_archive(seven_z)
    manifest.save_local(date, members, str(seven_z))
    print(f"已写入本地 manifest: {config.local_manifest_path(date)} ({len(members)} 条)")
    if upload:
        manifest.upload_to_r2(date, members, str(seven_z))
        print(f"已上传: {config.manifest_object_key(date)}")
    return len(members)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="为 .7z 生成 manifest.parquet")
    parser.add_argument("--date", required=True, help="交易日，如 20260803")
    parser.add_argument("--upload", action="store_true", help="同时上传到当前 STORAGE_BACKEND")
    args = parser.parse_args(argv)
    n = build(args.date, upload=args.upload)
    print(f"完成，共 {n} 条成员")


if __name__ == "__main__":
    main()
