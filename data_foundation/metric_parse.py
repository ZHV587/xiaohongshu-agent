"""中文计数单位感知的数值解析(单一事实源)。

为什么单独成模块:点赞/收藏等效果数在飞书/小红书常存成带单位的文本(如 "1.2万"、"10w+"、
"999+"、"1,234")。历史上 feishu_metrics / local_cards / online_notes / search_ranker 各有一份
只认纯数字的解析,把 "1.2万" 静默丢成 0/跳过 —— 而这恰是最高价值的爆款笔记,导致效果排序对它们
反转。这里提供唯一权威解析器,四处入口共用,杜绝逐点打补丁式的不一致。

纯函数、零依赖。解析失败返回 None(调用方按各自语义转 0 或跳过)。
"""
from __future__ import annotations

import math
import re
from typing import Any

# 中文/英文计数单位 → 乘数。万=1e4、亿=1e8;w/k 为口语缩写。大小写不敏感。
_UNIT_MULTIPLIERS: dict[str, float] = {
    "万": 1e4,
    "w": 1e4,
    "萬": 1e4,  # 繁体
    "亿": 1e8,
    "億": 1e8,  # 繁体
    "k": 1e3,
    "千": 1e3,
}

# 形如 "1.2万" / "10w+" / "1,234" / "999+" / "  3.5 万 " 的宽松匹配:
# 可选千分逗号的数字主体 + 可选单位 + 可选 "+" 后缀。
_NUM_UNIT_RE = re.compile(
    r"^\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([万萬亿億wWkK千]?)\s*\+?\s*$"
)


def parse_count(value: Any) -> float | None:
    """把任意计数值(数字或带单位文本)解析为有限非负 float;不可解析/负值 → None。

    支持:int/float 原值;字符串 "1234"、"1,234"、"1.2万"、"10w+"、"3亿"、"999+"。
    bool 显式按非数处理(避免 True→1)。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        match = _NUM_UNIT_RE.match(value)
        if not match:
            return None
        body, unit = match.group(1), match.group(2)
        try:
            number = float(body.replace(",", ""))
        except ValueError:
            return None
        if unit:
            number *= _UNIT_MULTIPLIERS[unit.lower()]
    else:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def parse_count_int(value: Any) -> int:
    """parse_count 的整数版:解析失败/负值 → 0。供卡片展示等只需非负整数的场景。"""
    number = parse_count(value)
    if number is None:
        return 0
    return int(number)


# 互动加权系数(单一事实源)。曾经效果回填(performance_feedback._score,存为 measured_by 边权重
# 且作为 analytics「score」)与检索重排序(search_ranker p_score)各写一套系数——回填用
# likes+2collects+3comments+4shares+5conversions,重排序只用 likes+2collects+5comments——
# 同一个「效果强度」概念口径分歧。这里统一系数;两处的「归一化」各自保留(回填÷播放量得转化率、
# 重排序对数归一化得绝对声量),只消除系数不一致。
ENGAGEMENT_WEIGHTS: dict[str, float] = {
    "likes": 1.0,
    "collects": 2.0,
    "comments": 3.0,
    "shares": 4.0,
    "conversions": 5.0,
}


def weighted_engagement(metrics: Any) -> float:
    """按统一系数计算加权互动总量(绝对值,未做任何归一化)。

    非数值/带单位文本经 parse_count 统一解析,解析失败按 0 计,绝不让脏数据中断计算。
    调用方在此基础上各自归一化:效果回填÷播放量(转化率)、检索重排序对数归一化(绝对声量)。
    """
    if not isinstance(metrics, dict):
        return 0.0
    total = 0.0
    for key, weight in ENGAGEMENT_WEIGHTS.items():
        value = parse_count(metrics.get(key))
        if value is not None:
            total += weight * value
    return total
