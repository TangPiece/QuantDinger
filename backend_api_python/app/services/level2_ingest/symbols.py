"""转换和上传时保留哪些代码。

默认是 A 股加上场内基金。可转债、B 股不进批量 Parquet。
"""
from __future__ import annotations


def is_equity(code: str) -> bool:
    """深市 0/3、沪市 6 视为 A 股。"""
    text = str(code).split(".")[0]
    return len(text) == 6 and text[:1] in ("0", "3", "6")


def is_fund(code: str) -> bool:
    """场内基金：沪市 5 开头，深市 15/16/17/18。不含可转债。"""
    text = str(code).split(".")[0]
    if len(text) != 6:
        return False
    if text[:1] == "5":
        return True
    return text.startswith(("15", "16", "17", "18"))


def is_default_symbol(code: str) -> bool:
    """批量转换默认保留的代码：A 股或场内基金。"""
    return is_equity(code) or is_fund(code)
