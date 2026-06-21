"""飞书多维表格只读工具（读取爆款数据）。

统一走 lark_cli（lark-cli base ...），与写操作保持一致的认证路径：
- Server 模式：自动注入用户 UAT（user_access_token），以用户身份读取
- CLI/Bot 降级：注入 FEISHU_APP_ID/SECRET 以机器人身份读取

多表聚合：自动列出 App 下所有数据表并逐表读取，每条记录带上来源
table_id / table_name，沉淀到 Postgres 后由 agent 统一检索。
"""
import os
import json
import shlex
import hashlib
from typing import Any

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

# 噪声列剔除：只砍掉确定对“分析爆款 + 写文案”无价值、且占体积的列
# （附件/图片/链接/封面/采集系统字段等）。不再用窄白名单，避免把不同表的
# 有效业务字段误删（21 张表字段结构各异）。
_EXCLUDE_COLUMN_KEYWORDS = (
    "图片",
    "附件",
    "封面",
    "链接",
    "网址",
    "域名",
    "二维码",
    "头像",
    "logo",
    "trace",
    "提示词",
)


def _is_noise_column(name: str) -> bool:
    return any(kw in name for kw in _EXCLUDE_COLUMN_KEYWORDS)


def _filter_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """剔除噪声列,保留其余业务字段;同时丢掉空值。"""
    return {
        name: value
        for name, value in fields.items()
        if value not in (None, "", [], {}) and not _is_noise_column(name)
    }


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


def list_base_tables(app_token: str, config: RunnableConfig = None) -> tuple[list[dict[str, str]], str | None]:
    """列出多维表 App 下所有数据表,返回 ([{table_id, name}], error)。"""
    from tools.lark_cli import lark_cli

    tables: list[dict[str, str]] = []
    page_token = ""
    while True:
        args = ["base", "+table-list", "--base-token", app_token, "--page-size", "100"]
        if page_token:
            args += ["--page-token", page_token]
        resp = lark_cli.func(shlex.join(args), config=config)
        if resp.startswith("Error") or resp.startswith("⚠️") or resp.startswith("Feishu"):
            return tables, f"lark-cli 列出数据表失败：{resp}"
        try:
            block = json.loads(resp).get("data", {})
        except json.JSONDecodeError:
            return tables, f"lark-cli 列表表返回非 JSON：{resp[:200]}"
        for item in block.get("items", []) or []:
            tid = item.get("table_id")
            if tid:
                tables.append({"table_id": str(tid), "name": str(item.get("name") or tid)})
        page_token = block.get("page_token") or ""
        if not block.get("has_more") or not page_token:
            break
    return tables, None


# PLACEHOLDER_READ_TABLE


def _read_single_table(
    *, app_token: str, table_id: str, table_name: str, config: RunnableConfig = None
) -> tuple[list[dict[str, Any]], str | None]:
    """读取单张表的全部记录,返回 (sync_rows, error)。每行带 table_id/table_name。"""
    from tools.lark_cli import lark_cli

    sync_rows: list[dict[str, Any]] = []
    offset = 0
    limit = 200
    while True:
        args = [
            "base", "+record-list",
            "--base-token", app_token,
            "--table-id", table_id,
            "--limit", str(limit),
            "--offset", str(offset),
        ]
        resp = lark_cli.func(shlex.join(args), config=config)
        if resp.startswith("Error") or resp.startswith("⚠️") or resp.startswith("Feishu"):
            return sync_rows, f"表[{table_name}] 读取失败：{resp}"
        try:
            block = json.loads(resp)["data"]
        except (json.JSONDecodeError, KeyError):
            return sync_rows, f"表[{table_name}] 返回非预期 JSON：{resp[:200]}"

        items = block.get("items")
        if isinstance(items, list):
            page_count = len(items)
            for item in items:
                fields_dict = item.get("fields") if isinstance(item, dict) else None
                record_id = item.get("record_id") if isinstance(item, dict) else None
                if not isinstance(fields_dict, dict) or not record_id:
                    continue
                filtered = _filter_fields(fields_dict)
                if not filtered:
                    continue
                row = {
                    "record_id": str(record_id),
                    "identity_kind": "feishu_record_id",
                    "table_id": table_id,
                    "table_name": table_name,
                    "fields": filtered,
                }
                ext = _external_updated_at(item)
                if ext is not None:
                    row["external_updated_at"] = ext
                sync_rows.append(row)
        else:
            fields_names = block.get("fields", [])
            rows_data = block.get("data", [])
            page_count = len(rows_data)
            for row_values in rows_data:
                fields_dict = {
                    fields_names[i]: row_values[i]
                    for i in range(min(len(fields_names), len(row_values)))
                    if row_values[i] is not None
                }
                filtered = _filter_fields(fields_dict)
                if not filtered:
                    continue
                sync_rows.append({
                    "record_id": _snapshot_id({**filtered, "__table__": table_id}),
                    "identity_kind": "content_snapshot",
                    "table_id": table_id,
                    "table_name": table_name,
                    "fields": filtered,
                })

        if block.get("has_more") and page_count > 0:
            offset += limit
        else:
            break
    return sync_rows, None


@tool
def read_xhs_data(scope: str = "all", config: RunnableConfig = None) -> dict[str, Any]:
    """读取飞书多维表格 App 下所有数据表的小红书爆款/对标数据(多表聚合)。

    自动发现 App 下全部数据表并逐表读取,返回聚合后的所有数据行。每行带来源
    table_name,供你分析爆款规律、提炼选题与文案套路。

    Args:
        scope: 读取范围,固定聚合全部表,传 "all" 即可。

    Returns:
        {"rows": [{table_name, fields}...], "sync_rows": [...], "tables": [...], "source_errors": [...]}
    """
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
    if not app_token:
        return {
            "error": "环境变量缺失：FEISHU_BITABLE_APP_TOKEN 未配置。",
            "rows": [], "sync_rows": [], "tables": [], "source_errors": [],
            "app_token": app_token,
        }

    tables, list_err = list_base_tables(app_token, config=config)
    if list_err:
        return {
            "error": list_err,
            "rows": [], "sync_rows": [], "tables": [], "source_errors": [list_err],
            "app_token": app_token,
        }

    all_sync_rows: list[dict[str, Any]] = []
    source_errors: list[str] = []
    table_summary: list[dict[str, Any]] = []
    for t in tables:
        rows, err = _read_single_table(
            app_token=app_token, table_id=t["table_id"], table_name=t["name"], config=config
        )
        if err:
            source_errors.append(err)
        all_sync_rows.extend(rows)
        table_summary.append({"table_id": t["table_id"], "name": t["name"], "rows": len(rows)})

    return {
        "rows": [{"table_name": r["table_name"], "fields": r["fields"]} for r in all_sync_rows],
        "sync_rows": all_sync_rows,
        "tables": table_summary,
        "source_errors": source_errors,
        "app_token": app_token,
    }

