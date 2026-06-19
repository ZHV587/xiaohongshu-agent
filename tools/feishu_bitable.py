"""飞书多维表格只读工具（读取爆款数据）。

统一走 lark_cli（lark-cli base +record-list），与写操作保持一致的认证路径：
- Server 模式：自动注入用户 UAT（user_access_token），以用户身份读取
- CLI/Bot 降级：注入 FEISHU_APP_ID/SECRET 以机器人身份读取

核心列白名单过滤在 Python 侧完成（减少 token 消耗）。
"""
import os
import json
import shlex
import hashlib
from typing import Any

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

# 核心列白名单关键词：只保留对"分析爆款规律 + 写文案"有用的列，
# 砍掉图片附件/链接/仿写流程/采集系统等噪声列（占数据体积大头却无分析价值）。
_CORE_COLUMN_KEYWORDS = (
    "标题",
    "正文",
    "视频文案",
    "话题标签",
    "分类标签",
    "点赞",
    "收藏",
    "评论数",
    "转发",
    "播放",
    "赞评比",
    "赞藏比",
    "爆款",
    "博主",
    "发布时间",
    "关联搜索词",
)

# 明确排除的噪声关键词（优先级高于白名单：命中即剔除）。
_EXCLUDE_COLUMN_KEYWORDS = (
    "仿写",
    "图片",
    "附件",
    "链接",
    "域名",
    "采集",
    "封面",
    "海外",
    "修正",
    "隐藏",
)


def _is_core_column(name: str) -> bool:
    """判断列是否属于核心分析列（先排除噪声，再匹配白名单）。"""
    if any(kw in name for kw in _EXCLUDE_COLUMN_KEYWORDS):
        return False
    return any(kw in name for kw in _CORE_COLUMN_KEYWORDS)


def _filter_rows(rows: list[dict], core_only: bool) -> tuple[list[str], list[dict]]:
    """从记录列表提取列名并按白名单过滤。"""
    seen: dict[str, None] = {}
    for row in rows:
        seen.update(dict.fromkeys(row))
    columns = list(seen)

    if core_only:
        core_cols = [c for c in columns if _is_core_column(c)]
        columns = core_cols
        rows = [{c: r.get(c) for c in core_cols if c in r} for r in rows]

    return columns, rows


def _snapshot_id(fields: dict[str, Any]) -> str:
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"snapshot:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _external_updated_at(item: dict[str, Any]) -> Any | None:
    return (
        item.get("last_modified_time")
        or item.get("modified_time")
        or item.get("updated_time")
        or item.get("update_time")
    )


@tool
def read_xhs_data(scope: str = "all", config: RunnableConfig = None) -> dict[str, Any]:
    """读取飞书多维表格里的小红书爆款/对标数据。

    返回整表的列名清单与所有数据行，供你分析爆款规律、提炼选题与文案套路。
    你需要自行理解每一列的含义（如标题、正文、点赞、收藏、话题标签等）。

    Args:
        scope: 读取范围，目前固定读取整张表，传 "all" 即可。

    Returns:
        {"columns": [列名...], "rows": [{列名: 值, ...}, ...]}
    """
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
    table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID", "")
    if not app_token or not table_id:
        return {
            "error": "环境变量缺失：FEISHU_BITABLE_APP_TOKEN 或 FEISHU_BITABLE_TABLE_ID 未配置。",
            "columns": [],
            "rows": [],
            "sync_rows": [],
            "app_token": app_token,
            "table_id": table_id,
        }

    from tools.lark_cli import lark_cli  # 延迟 import，避免循环依赖

    all_rows: list[dict] = []
    all_sync_rows: list[dict[str, Any]] = []
    offset = 0
    limit = 200

    # 分页拉取全表记录
    while True:
        args = [
            "base", "+record-list",
            "--base-token", app_token,
            "--table-id", table_id,
            "--limit", str(limit),
            "--offset", str(offset),
        ]

        command = shlex.join(args)
        resp = lark_cli.func(command, config=config)

        # lark_cli 出错时返回以 "Error" 或 "⚠️" 开头的字符串
        if resp.startswith("Error") or resp.startswith("⚠️") or resp.startswith("Feishu"):
            return {
                "error": f"lark-cli 读取多维表格失败：{resp}",
                "columns": [],
                "rows": [],
                "sync_rows": [],
                "app_token": app_token,
                "table_id": table_id,
            }

        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            return {
                "error": f"lark-cli 返回非 JSON 格式：{resp[:300]}",
                "columns": [],
                "rows": [],
                "sync_rows": [],
                "app_token": app_token,
                "table_id": table_id,
            }

        # lark-cli may return native records or a compact matrix.
        block = data["data"]
        items = block.get("items")
        if isinstance(items, list):
            page_rows_count = len(items)
            for item in items:
                fields_dict = item.get("fields") if isinstance(item, dict) else None
                record_id = item.get("record_id") if isinstance(item, dict) else None
                if not isinstance(fields_dict, dict) or not record_id:
                    continue
                _, filtered = _filter_rows([fields_dict], core_only=True)
                filtered_fields = filtered[0]
                all_rows.append(filtered_fields)
                sync_row = {
                    "record_id": str(record_id),
                    "identity_kind": "feishu_record_id",
                    "fields": filtered_fields,
                }
                external_updated_at = _external_updated_at(item)
                if external_updated_at is not None:
                    sync_row["external_updated_at"] = external_updated_at
                all_sync_rows.append(sync_row)
        else:
            fields_names = block.get("fields", [])
            rows_data = block.get("data", [])
            page_rows_count = len(rows_data)
            for row in rows_data:
                fields_dict = {
                    fields_names[i]: row[i]
                    for i in range(min(len(fields_names), len(row)))
                    if row[i] is not None
                }
                _, filtered = _filter_rows([fields_dict], core_only=True)
                filtered_fields = filtered[0]
                all_rows.append(filtered_fields)
                all_sync_rows.append({
                    "record_id": _snapshot_id(filtered_fields),
                    "identity_kind": "content_snapshot",
                    "fields": filtered_fields,
                })

        # 分页：若 has_more 且本页有数据，增加 offset 并继续
        if block.get("has_more") and page_rows_count > 0:
            offset += limit
        else:
            break

    columns, rows = _filter_rows(all_rows, core_only=True)
    return {
        "columns": columns,
        "rows": rows,
        "sync_rows": all_sync_rows,
        "source_errors": [],
        "app_token": app_token,
        "table_id": table_id,
    }
