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
            "+record-upsert",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(fields_payload, ensure_ascii=False),
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
            "+record-upsert",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(fields_payload, ensure_ascii=False),
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
        "+record-upsert",
        "--base-token",
        app_token,
        "--table-id",
        table_id,
        "--json",
        json.dumps(fields_payload, ensure_ascii=False),
    ])
    parsed = _parse_lark_json(lark_cli.func(command, config=config))
    if not parsed["ok"]:
        return parsed

    data = parsed["data"]
    record_id = data.get("data", {}).get("record", {}).get("record_id") or data.get("data", {}).get("record_id") or ""
    
    # 额外逻辑：向飞书 Wiki 权威空间同步沉淀一份精美的 Docx 知识文档
    wiki_space_id = os.environ.get("FEISHU_WIKI_SPACE_ID", "7648177996175543260")
    wiki_title = f"【诊断定位】{project_name} - {title}"
    
    wiki_url = None
    try:
        # 步骤 A: 创建空 Wiki 节点
        create_command = shlex.join([
            "wiki", "+node-create",
            "--space-id", wiki_space_id,
            "--title", wiki_title,
            "--obj-type", "docx",
            "--as", "user"
        ])
        wiki_parsed = _parse_lark_json(lark_cli.func(create_command, config=config))
        if wiki_parsed["ok"]:
            node_data = wiki_parsed["data"].get("data", {}).get("node", {}) or wiki_parsed["data"].get("data", {})
            obj_token = node_data.get("obj_token") or node_data.get("node", {}).get("obj_token")
            if obj_token:
                # 步骤 B: 覆写 Markdown 正文
                overwrite_command = shlex.join([
                    "docs", "+update",
                    "--doc", obj_token,
                    "--command", "overwrite",
                    "--doc-format", "markdown",
                    "--content", content,
                    "--as", "user"
                ])
                lark_cli.func(overwrite_command, config=config)
                wiki_url = node_data.get("url")
    except Exception:
        # Wiki 同步是协作层，若发生偶发故障不应该阻断多维表格的主链路
        pass

    return {
        "ok": True,
        "record_id": record_id,
        "redirect_url": f"https://feishu.cn/base/{app_token}?table={table_id}",
        "wiki_url": wiki_url,
    }


DEFAULT_COLLECT_TABLE_ID = "tbl24vSVeLvz45ig"  # 🧲单篇采集库(§8 笔记级白名单)


def create_online_note_record(
    note: dict[str, Any],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """把一条线上笔记写入飞书爆款采集库(`FEISHU_BITABLE_COLLECT_TABLE_ID`)。

    列名与 §8 COLUMN_TO_METRIC 反向对齐(点赞数/收藏数/评论数/转发数);其余列用明文默认,
    可经 XHS_COLLECT_FIELD_* 覆盖。**不复用** FEISHU_BITABLE_TABLE_ID(草稿/选题表)。
    去重由调用方(adopt 编排)按 Postgres mapping 保证,此函数只负责写。
    """
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    table_id = os.environ.get("FEISHU_BITABLE_COLLECT_TABLE_ID", DEFAULT_COLLECT_TABLE_ID)
    if not app_token or not table_id:
        return {"ok": False, "error": "FEISHU_BITABLE_APP_TOKEN and FEISHU_BITABLE_COLLECT_TABLE_ID are required"}

    f = lambda key, default: os.environ.get(key, default)  # noqa: E731
    tags = note.get("tags") or []
    tags_text = " ".join(f"#{t.lstrip('#')}" for t in tags if str(t).strip()) if isinstance(tags, list) else str(tags)
    fields_payload: dict[str, Any] = {
        f("XHS_COLLECT_FIELD_TITLE", "标题"): str(note.get("title") or ""),
        f("XHS_COLLECT_FIELD_BODY", "正文"): str(note.get("summary") or ""),
        f("XHS_COLLECT_FIELD_AUTHOR", "博主"): str(note.get("author") or ""),
        f("XHS_COLLECT_FIELD_COVER", "封面链接"): str(note.get("cover_url") or ""),
        f("XHS_COLLECT_FIELD_NOTE_URL", "原文链接"): str(note.get("note_url") or ""),
        f("XHS_COLLECT_FIELD_TAGS", "话题标签"): tags_text,
        f("XHS_COLLECT_FIELD_PUBLISHED", "发布时间"): str(note.get("created_at") or ""),
        f("XHS_COLLECT_FIELD_PLATFORM", "采集平台"): "线上实时",
        "点赞数": int(note.get("likes") or 0),
        "收藏数": int(note.get("collects") or 0),
        "评论数": int(note.get("comments") or 0),
        "转发数": int(note.get("shares") or 0),
    }
    # 丢空值,避免给飞书写空串触发类型校验
    fields_payload = {k: v for k, v in fields_payload.items() if v not in ("", None)}

    command = shlex.join([
        "base",
        "+record-upsert",
        "--base-token",
        app_token,
        "--table-id",
        table_id,
        "--json",
        json.dumps(fields_payload, ensure_ascii=False),
    ])
    parsed = _parse_lark_json(lark_cli.func(command, config=config))
    if not parsed["ok"]:
        return parsed
    data = parsed["data"]
    record_id = (
        data.get("data", {}).get("record", {}).get("record_id")
        or data.get("data", {}).get("record_id")
        or ""
    )
    return {"ok": True, "record_id": record_id, "table_id": table_id}


feishu_action_tools = [
    sync_copy_to_feishu,
    send_review_notification,
    sync_topic_to_feishu,
    sync_diagnosis_to_feishu,
]

