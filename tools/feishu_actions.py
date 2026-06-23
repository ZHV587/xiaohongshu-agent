from __future__ import annotations

import json
import os
import shlex
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from tools.lark_cli import lark_cli


def _parse_lark_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "Lark CLI returned invalid JSON", "raw": raw}

    if not isinstance(data, dict):
        return {"ok": False, "error": "Lark CLI returned an unexpected JSON response", "raw": raw}
    if data.get("code") not in (None, 0):
        return {"ok": False, "error": data.get("msg") or data.get("message") or "Lark API failed"}
    return {"ok": True, "data": data}


@tool
def sync_copy_to_feishu(
    title: str,
    content: str,
    tags: str | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Create a Feishu Base draft record for the generated Xiaohongshu copy."""
    if not title.strip() or not content.strip():
        return {"ok": False, "error": "title and content are required"}

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID")
    if not app_token or not table_id:
        return {"ok": False, "error": "FEISHU_BITABLE_APP_TOKEN and FEISHU_BITABLE_TABLE_ID are required"}

    title_field = os.environ.get("XHS_BITABLE_FIELD_TITLE", "标题")
    body_field = os.environ.get("XHS_BITABLE_FIELD_BODY", "正文内容")
    tags_field = os.environ.get("XHS_BITABLE_FIELD_TAGS", "标签")
    author_field = os.environ.get("XHS_BITABLE_FIELD_AUTHOR", "创建人")
    status_field = os.environ.get("XHS_BITABLE_FIELD_STATUS", "状态")
    fields_payload: dict[str, Any] = {
        title_field: title,
        body_field: content,
        author_field: "agent",
        status_field: "草稿",
    }
    if tags:
        fields_payload[tags_field] = tags

    command = shlex.join(
        [
            "base",
            "+record-create",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps({"fields": fields_payload}, ensure_ascii=False),
        ]
    )
    parsed = _parse_lark_json(lark_cli.func(command, config=config))
    if not parsed["ok"]:
        return parsed

    data = parsed["data"]
    record_id = data.get("data", {}).get("record", {}).get("record_id") or data.get("data", {}).get("record_id") or ""
    return {
        "ok": True,
        "record_id": record_id,
        "redirect_url": f"https://feishu.cn/base/{app_token}?table={table_id}",
    }


@tool
def send_review_notification(
    chat_id: str,
    title: str,
    content: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Send a Feishu group card asking reviewers to check a generated draft."""
    if not chat_id.strip() or not title.strip() or not content.strip():
        return {"ok": False, "error": "chat_id, title and content are required"}

    card_content = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "小红书笔记待审核"},
            "template": "red",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**选题标题**：\\n{title}\\n\\n**笔记正文草稿**：\\n{content}",
                },
            },
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": "请前往小红书智能体文案工作台确认发布。"}],
            },
        ],
    }
    command = shlex.join(
        [
            "im",
            "+messages-send",
            "--chat-id",
            chat_id,
            "--msg-type",
            "interactive",
            "--content",
            json.dumps(card_content, ensure_ascii=False),
        ]
    )
    parsed = _parse_lark_json(lark_cli.func(command, config=config))
    if not parsed["ok"]:
        return parsed
    return {"ok": True}


@tool
def sync_topic_to_feishu(
    direction: str,
    topics: list[str],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Create Feishu Base records for the generated Xiaohongshu topic suggestions."""
    if not direction.strip() or not topics:
        return {"ok": False, "error": "direction and topics are required"}
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    if not app_token:
        return {"ok": False, "error": "FEISHU_BITABLE_APP_TOKEN is required"}

    table_id = os.environ.get("FEISHU_BITABLE_TOPIC_TABLE_ID")
    if not table_id:
        from tools.feishu_bitable import list_base_tables
        tables, err = list_base_tables(app_token, config=config)
        if not err and tables:
            for t in tables:
                if "选题" in t["name"] or "topic" in t["name"].lower():
                    table_id = t["table_id"]
                    break
        if not table_id:
            table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID")

    if not table_id:
        return {"ok": False, "error": "No valid table_id found for topics"}

    created_records = []
    for topic in topics:
        fields_payload = {
            "选题方向": direction,
            "选题名称": topic,
            "状态": "待撰写",
        }
        if table_id == os.environ.get("FEISHU_BITABLE_TABLE_ID"):
            title_field = os.environ.get("XHS_BITABLE_FIELD_TITLE", "标题")
            fields_payload = {
                title_field: f"【选题】{topic}",
                "状态": "草稿"
            }

        command = shlex.join([
            "base",
            "+record-create",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps({"fields": fields_payload}, ensure_ascii=False),
        ])
        parsed = _parse_lark_json(lark_cli.func(command, config=config))
        if parsed["ok"]:
            data = parsed["data"]
            record_id = data.get("data", {}).get("record", {}).get("record_id") or data.get("data", {}).get("record_id") or ""
            created_records.append(record_id)

    return {
        "ok": True,
        "record_ids": created_records,
        "redirect_url": f"https://feishu.cn/base/{app_token}?table={table_id}",
    }


@tool
def sync_diagnosis_to_feishu(
    project_name: str,
    title: str,
    content: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Create a Feishu Base record or document for account positioning and commercial diagnosis."""
    if not project_name.strip() or not content.strip():
        return {"ok": False, "error": "project_name and content are required"}
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    if not app_token:
        return {"ok": False, "error": "FEISHU_BITABLE_APP_TOKEN is required"}

    table_id = None
    from tools.feishu_bitable import list_base_tables
    tables, err = list_base_tables(app_token, config=config)
    if not err and tables:
        for t in tables:
            if any(kw in t["name"] for kw in ["诊断", "定位", "会话", "diagnosis", "positioning"]):
                table_id = t["table_id"]
                break
    if not table_id:
        table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID")

    if not table_id:
        return {"ok": False, "error": "No valid table_id found for diagnosis"}

    fields_payload = {
        "项目名称": project_name,
        "诊断主题": title,
        "诊断详情": content,
    }
    if table_id == os.environ.get("FEISHU_BITABLE_TABLE_ID"):
        title_field = os.environ.get("XHS_BITABLE_FIELD_TITLE", "标题")
        body_field = os.environ.get("XHS_BITABLE_FIELD_BODY", "正文内容")
        fields_payload = {
            title_field: f"【诊断定位】{project_name} - {title}",
            body_field: content,
        }

    command = shlex.join([
        "base",
        "+record-create",
        "--base-token",
        app_token,
        "--table-id",
        table_id,
        "--json",
        json.dumps({"fields": fields_payload}, ensure_ascii=False),
    ])
    parsed = _parse_lark_json(lark_cli.func(command, config=config))
    if not parsed["ok"]:
        return parsed

    data = parsed["data"]
    record_id = data.get("data", {}).get("record", {}).get("record_id") or data.get("data", {}).get("record_id") or ""
    return {
        "ok": True,
        "record_id": record_id,
        "redirect_url": f"https://feishu.cn/base/{app_token}?table={table_id}",
    }


feishu_action_tools = [
    sync_copy_to_feishu,
    send_review_notification,
    sync_topic_to_feishu,
    sync_diagnosis_to_feishu,
]

