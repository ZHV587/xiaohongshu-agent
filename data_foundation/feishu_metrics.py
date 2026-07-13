"""飞书结构化效果列 → 标准 metrics 的抽取层(feishu-performance-metrics)。

把已在库的飞书爆款效果列(点赞/收藏/评论/转发/播放)按**明文表白名单 + 列名映射**
转成标准 metrics,供 save_performance_metric_resource 写入 performance_metric + measured_by。

纯函数、零 LLM、零 I/O:仅依据 (table_id, table_name, fields) 决定产物。
回填脚本与 sync_base_rows 同步期接通**共用本函数**(单一事实源)。

白名单与列映射是明文常量(用户坚持明文配置):扩表/改列名直接改本模块,不引入运行时开关。
"""
from __future__ import annotations

from typing import Any

from data_foundation.metric_parse import parse_count

# 笔记级表 id 白名单(按 table_id 精确匹配,不依赖易变中文表名)。
# 仅这些表的记录抽取笔记效果;评论级/词库/选题分类等表不抽。
NOTE_LEVEL_TABLE_IDS: frozenset[str] = frozenset({
    "tbl24vSVeLvz45ig",  # 🧲单篇采集库
    "tblXDHL8hBrUUMI2",  # 📝博主笔记库
    "tblX58JrbsqczqPl",  # 🔥爆款搜索
    "tblMUqaUokINcdIK",  # 📊流量监测库
})
# 明确排除(由"不在白名单"自然排除,此处仅作语义备注):
#   tblZgH0SF0AfYIpV 💬评论采集库 —— "点赞数"是评论点赞、非笔记效果,必须排除。

# 列名 → 标准 metric。取值为 performance_feedback.ALLOWED_METRICS 子集，与统一精排口径一致。
COLUMN_TO_METRIC: dict[str, str] = {
    "点赞数": "likes",
    "收藏数": "collects",
    "评论数": "comments",
    "转发数": "shares",
    "播放量": "views",
}


def _coerce_non_negative_number(value: Any) -> int | float | None:
    """把飞书字段值解析为有限非负数;不可解析/负值/非数值 → None(跳过该 metric)。

    经 parse_count 统一处理,支持 "1.2万"/"10w+" 等中文计数单位(否则爆款数值被丢成 None,
    效果排序对最高价值笔记反转)。整数值返回 int 以保持既有写入形态。
    """
    number = parse_count(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else number


def extract_performance_metrics(
    table_id: str,
    table_name: str,
    fields: dict[str, Any] | None,
) -> dict[str, int | float] | None:
    """白名单外或无有效 metric → None;否则 → {metric: 非负数值}。纯函数,无副作用。"""
    if table_id not in NOTE_LEVEL_TABLE_IDS:
        return None
    fields = fields or {}
    metrics: dict[str, int | float] = {}
    for column, metric in COLUMN_TO_METRIC.items():
        number = _coerce_non_negative_number(fields.get(column))
        if number is not None:
            metrics[metric] = number
    return metrics or None


__all__ = ["NOTE_LEVEL_TABLE_IDS", "COLUMN_TO_METRIC", "extract_performance_metrics"]
