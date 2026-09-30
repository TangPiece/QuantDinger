"""三类 CSV 的列定义与规范化规则。

规范化遵循「忠实转换」原则：只做格式修正（补零时间、去空列、数值列定型），
不剔除任何业务行（撤单/状态行全部保留，供后续撤单率、委托成交率计算）。

字段语义依据官方文档 `明细使用说明/各代码的意义.docx`：
- 价格单位 = 整数 × 0.0001 元（`106200` = 10.62 元）
- 金额(元) = 价格 × 数量 / 10000
"""
from __future__ import annotations

import pandas as pd


def _depth_cols(prefix: str) -> list[str]:
    """生成 10 档盘口列名，如 `申卖价1`..`申卖价10`。"""
    return [f"{prefix}{i}" for i in range(1, 11)]


# 各文件需要规范化为 float64 的数值列；其余列保持字符串（代码/编号/日期/时间/标志）
NUMERIC_COLUMNS: dict[str, list[str]] = {
    "逐笔成交": ["成交价格", "成交数量"],
    "逐笔委托": ["委托价格", "委托数量"],
    "行情": [
        "成交价", "成交量", "成交额", "成交笔数",
        "当日累计成交量", "当日成交额",
        "最高价", "最低价", "开盘价", "前收盘",
        *_depth_cols("申卖价"), *_depth_cols("申卖量"),
        *_depth_cols("申买价"), *_depth_cols("申买量"),
        "加权平均叫卖价", "加权平均叫买价",
        "叫卖总量", "叫买总量",
        "不加权指数", "品种总数", "上涨品种数", "下跌品种数", "持平品种数",
    ],
}


def normalize(df: pd.DataFrame, ftype: str) -> pd.DataFrame:
    """对读入的 DataFrame 做忠实规范化。

    1. 删除每行末尾多余逗号产生的 `Unnamed` 空列
    2. `时间` 统一补零到 9 位（上午 9 点丢前导 0，如 `91556440` → `091556440`）
    3. 数值列转 float64（空值转为 NaN）

    返回规范化后的 DataFrame（不改动调用方传入的对象）。
    """
    df = df.copy()

    # 删除空列：CSV 每行末尾多一个逗号，pandas 会生成 Unnamed 列
    df = df[[c for c in df.columns if not str(c).startswith("Unnamed")]]

    # 时间补零：`时间` 为 HHMMSSmmm，上午小时无前导 0，需统一为 9 位保证字符串比较正确
    if "时间" in df.columns:
        df["时间"] = df["时间"].astype(str).str.zfill(9)

    # 数值列定型：价格/数量/额转 float64，空值 → NaN
    for col in NUMERIC_COLUMNS.get(ftype, []):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    return df
