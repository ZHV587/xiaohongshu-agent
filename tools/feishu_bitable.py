"""飞书多维表格只读工具（读取爆款数据）。

统一走 lark_cli（lark-cli base ...），与写操作保持一致的认证路径：
- Server 模式：自动注入用户 UAT（user_access_token），以用户身份读取
- CLI/Bot 降级：注入 FEISHU_APP_ID/SECRET 以机器人身份读取

多表聚合：自动列出 App 下所有数据表并逐表读取，每条记录带上来源
table_id / table_name，沉淀到 Postgres 后由 agent 统一检索。
"""
import os
import json
import re
import shlex
import hashlib
from typing import Any

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

# 噪声列剔除（收窄版）：只按列名砍掉确定无价值的文本/系统列。
# 关键修正：移除了 图片/封面/链接/网址/域名 —— 这些其中的【文本】列(如「封面链接」
# 小红书 CDN 直链、「原文链接」markdown、「图片链接」「视频链接」)是卡片展示必需,
# 此前被一并丢弃是本地数据缺口的根因。附件【对象】列(含 file_token,有时效、非直链)
# 改由 _is_attachment_value 按【值形状】剔除,从而精准放行「封面链接」、剔除「封面」附件。
_EXCLUDE_COLUMN_KEYWORDS = (
    "附件",
    "二维码",
    "头像",
    "logo",
    "trace",
    "提示词",
    "设置",
)


def _is_noise_column(name: str) -> bool:
    return any(kw in name for kw in _EXCLUDE_COLUMN_KEYWORDS)


def _is_attachment_value(value: Any) -> bool:
    """按值形状识别飞书附件对象列:非空 list,且元素均为含 file_token 的 dict。

    附件对象(如「封面」)只有带时效的 tmp_url、无公网直链,对卡片无用;而「封面链接」
    是文本 CDN 直链,值是字符串 → 不命中此判定,得以保留。
    """
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(item, dict) and "file_token" in item for item in value)


def _filter_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """剔除噪声列(按列名 + 附件值形状),保留其余业务字段;同时丢掉空值。"""
    return {
        name: value
        for name, value in fields.items()
        if value not in (None, "", [], {})
        and not _is_noise_column(name)
        and not _is_attachment_value(value)
    }


# 封面/原文链接归一化(供同步落库与发现卡片 hydrate 共用)。
_COVER_FIELD_CANDIDATES = ("封面链接", "图片链接", "封面图链接", "首图链接")
_NOTE_URL_FIELD_CANDIDATES = ("原文链接", "笔记链接", "链接", "笔记地址")
_MARKDOWN_LINK_RE = re.compile(r"\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s)]+")


def _coerce_text(value: Any) -> str:
    """飞书文本列可能是 str,或 [{'text': ..., 'type': 'text'}] 富文本片段数组。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [seg.get("text", "") for seg in value if isinstance(seg, dict)]
        return "".join(parts)
    return ""


def _extract_url(value: Any) -> str:
    """从文本/markdown/富文本中提取第一个 http(s) URL;取不到返回原始文本。"""
    text = _coerce_text(value).strip()
    if not text:
        return ""
    md = _MARKDOWN_LINK_RE.search(text)
    if md:
        return md.group(1)
    bare = _BARE_URL_RE.search(text)
    if bare:
        return bare.group(0)
    return text


def extract_cover_url(fields: dict[str, Any]) -> str:
    """从一行字段里取归一化封面 URL(优先「封面链接」等文本直链列)。"""
    for key in _COVER_FIELD_CANDIDATES:
        if key in fields:
            url = _extract_url(fields[key])
            if url:
                return url
    return ""


def extract_note_url(fields: dict[str, Any]) -> str:
    """从一行字段里取归一化原文链接(从「原文链接」markdown 提取 URL)。"""
    for key in _NOTE_URL_FIELD_CANDIDATES:
        if key in fields:
            url = _extract_url(fields[key])
            if url:
                return url
    return ""


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
    offset = 0
    limit = 100
    while True:
        args = [
            "base", "+table-list",
            "--base-token", app_token,
            "--limit", str(limit),
            "--offset", str(offset),
        ]
        resp = lark_cli.func(shlex.join(args), config=config)
        if resp.startswith("Error") or resp.startswith("⚠️") or resp.startswith("Feishu"):
            return tables, f"lark-cli 列出数据表失败：{resp}"
        try:
            block = json.loads(resp).get("data", {})
        except json.JSONDecodeError:
            return tables, f"lark-cli 列表表返回非 JSON：{resp[:200]}"
        # lark-cli 返回 data.tables[{id, name}](与 record-list 的 items/table_id 不同)
        items = block.get("tables") or block.get("items") or []
        for item in items:
            tid = item.get("table_id") or item.get("id")
            if tid:
                tables.append({"table_id": str(tid), "name": str(item.get("name") or tid)})
        # table-list 一次性返回全部;仅在明确还有更多时继续翻页
        if block.get("has_more") and items:
            offset += limit
        else:
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
            record_ids = block.get("record_id_list") or []
            page_count = len(rows_data)
            for idx, row_values in enumerate(rows_data):
                fields_dict = {
                    fields_names[i]: row_values[i]
                    for i in range(min(len(fields_names), len(row_values)))
                    if row_values[i] is not None
                }
                filtered = _filter_fields(fields_dict)
                if not filtered:
                    continue
                # 矩阵格式优先用 record_id_list 的真实 ID;缺失才回退内容快照
                rid = record_ids[idx] if idx < len(record_ids) else None
                if rid:
                    sync_rows.append({
                        "record_id": str(rid),
                        "identity_kind": "feishu_record_id",
                        "table_id": table_id,
                        "table_name": table_name,
                        "fields": filtered,
                    })
                else:
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

