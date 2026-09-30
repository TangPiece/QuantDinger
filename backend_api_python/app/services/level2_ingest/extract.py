"""通过系统自带 bsdtar（`/usr/bin/tar`）处理 `.7z`。

整包解压到本地目录后，由 convert / pipeline 的 local 路径做转换或入库。
批量场景由上层保证：转完（并删源）再解下一包，避免多日 CSV 同时占满磁盘。

macOS 系统 `tar` 实为 bsdtar（libarchive），原生支持 7z，无需额外安装 py7zr/p7zip。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import config


def _normalize_member_path(raw: str) -> str:
    """去掉 tar 列表中的首尾空白与 `./` 前缀，便于布局判定。"""
    return raw.strip().lstrip("./")


def list_members(seven_z_path: str | Path) -> list[str]:
    """列出 `.7z` 内所有 `.csv` 成员路径（只读，不占磁盘）。

    支持两种布局：
    - `{date}/{code}/{ftype}.csv`
    - `{code}/{ftype}.csv`（无日期前缀，日期取自归档文件名）
    """
    out = subprocess.check_output(
        ["tar", "-tf", str(seven_z_path)], text=True
    )
    return [
        name
        for line in out.splitlines()
        if (name := _normalize_member_path(line)).endswith(".csv")
    ]


def _archive_has_date_prefix(seven_z_path: Path, date: str) -> bool:
    """判断归档内成员是否以 `{date}/` 为顶层前缀。

    任一条 csv 路径以该前缀开头即视为「带日期层」布局；
    无 csv 时回退到 `tar -tf` 首个非空路径。
    """
    prefix = f"{date}/"
    members = list_members(seven_z_path)
    if members:
        return any(m.startswith(prefix) for m in members)

    # 无 csv（异常包）时用完整列表里的首个非空路径判断
    out = subprocess.check_output(
        ["tar", "-tf", str(seven_z_path)], text=True
    )
    for line in out.splitlines():
        name = _normalize_member_path(line)
        if not name:
            continue
        return name == date or name == f"{date}/" or name.startswith(prefix)
    return False

def _looks_like_code_dir(name: str) -> bool:
    """股票代码目录启发式：含交易所后缀，如 000001.SZ。"""
    return "." in name and not name.startswith(".")


def _is_nested_date_layout(day_dir: Path, date: str) -> bool:
    """检测错误的双层日期：`day_dir/{date}/` 下才是股票代码目录。"""
    nested = day_dir / date
    if not nested.is_dir():
        return False
    nested_codes = [
        p for p in nested.iterdir() if p.is_dir() and _looks_like_code_dir(p.name)
    ]
    if not nested_codes:
        return False
    # 日目录顶层不应再直接有股票代码（否则是混合布局，不强行 flatten）
    top_codes = [
        p for p in day_dir.iterdir()
        if p.is_dir() and p.name != date and _looks_like_code_dir(p.name)
    ]
    return not top_codes


def _flatten_nested_date_dir(day_dir: Path, date: str) -> bool:
    """将 `day_dir/{date}/*` 上移到 `day_dir/`，消除双层日期。

    返回是否执行了展平。
    """
    if not _is_nested_date_layout(day_dir, date):
        return False

    nested = day_dir / date
    print(f"  展平双层日期目录: {nested} → {day_dir}", flush=True)
    for item in list(nested.iterdir()):
        dest = day_dir / item.name
        if dest.exists():
            raise FileExistsError(
                f"展平冲突：目标已存在 {dest}（源 {item}）"
            )
        shutil.move(str(item), str(dest))
    nested.rmdir()
    return True


def extract_archive(
    seven_z_path: str | Path,
    dest_root: str | Path | None = None,
) -> Path:
    """整包解压 `.7z` 到 `{dest_root}/{date}/`，返回当日目录路径。

    支持两种归档布局，最终都落到 `DATA_ROOT/{date}/{code}/{ftype}.csv`：
    - `{code}/{ftype}.csv`：解压到日目录下
    - `{date}/{code}/{ftype}.csv`：解压到 DATA_ROOT（避免再套一层日期）

    目标日目录已存在且为正常布局则跳过；若为双层日期脏数据则先展平再跳过。
    """
    seven_z_path = Path(seven_z_path)
    if not seven_z_path.is_file():
        raise FileNotFoundError(seven_z_path)

    root = Path(dest_root) if dest_root is not None else config.DATA_ROOT
    date = seven_z_path.stem
    day_dir = root / date

    # 已有非空日目录：优先修复双层脏数据，否则视为已解压完成
    if day_dir.is_dir() and any(day_dir.iterdir()):
        if _flatten_nested_date_dir(day_dir, date):
            print(f"  已修复双层目录，跳过解压: {day_dir}", flush=True)
            return day_dir
        print(f"  跳过解压（目录已存在）: {day_dir}", flush=True)
        return day_dir

    root.mkdir(parents=True, exist_ok=True)
    has_date_prefix = _archive_has_date_prefix(seven_z_path, date)

    if has_date_prefix:
        # 归档自带日期层：解到 DATA_ROOT，得到 {date}/{code}/...
        print(
            f"  整包解压 {seven_z_path.name} → {root}（归档含日期前缀）",
            flush=True,
        )
        subprocess.check_call(
            ["tar", "-xf", str(seven_z_path), "-C", str(root)]
        )
    else:
        # 无日期层：解到日目录，得到 {date}/{code}/...
        day_dir.mkdir(parents=True, exist_ok=True)
        print(f"  整包解压 {seven_z_path.name} → {day_dir}", flush=True)
        subprocess.check_call(
            ["tar", "-xf", str(seven_z_path), "-C", str(day_dir)]
        )

    # 兜底：若仍出现双层日期则展平
    _flatten_nested_date_dir(day_dir, date)

    if not day_dir.is_dir() or not any(day_dir.iterdir()):
        raise FileNotFoundError(f"解压后日目录为空: {day_dir}")
    return day_dir


def extract_member_bytes(seven_z_path: str | Path, member: str) -> bytes:
    """解压单个成员到内存，返回其原始字节（gb18030 编码的 CSV 内容）。

    供 manifest 构建等按需读取；入库/转换主路径改走整包解压。
    使用 `tar -xOf`：`-O` 解压到 stdout，`-f` 指定归档文件。
    """
    return subprocess.check_output(
        ["tar", "-xOf", str(seven_z_path), member]
    )


def parse_member(
    member: str,
    *,
    archive_date: str | None = None,
) -> tuple[str, str, str]:
    """解析成员路径为 (日期, 代码, 文件类型)。

    支持：
    - `20260803/000001.SZ/逐笔成交.csv`
    - `000001.SZ/逐笔成交.csv`（需提供 archive_date，通常为 .7z 文件名 stem）
    """
    parts = [p for p in member.strip("/").split("/") if p]
    if len(parts) == 3:
        date, code, fname = parts
    elif len(parts) == 2:
        if not archive_date:
            raise ValueError(
                f"成员路径缺少日期层，需传入 archive_date: {member!r}"
            )
        date = archive_date
        code, fname = parts
    else:
        raise ValueError(f"无法解析成员路径（期望 2 或 3 段）: {member!r}")
    if not fname.endswith(".csv"):
        raise ValueError(f"成员不是 csv: {member!r}")
    ftype = fname.rsplit(".csv", 1)[0]
    return date, code, ftype
