# tools/web_bridge_runner.py
import argparse
import sys
import os
import json
import shlex

# 确保项目根目录在 path 中，方便导入
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.uat_store import save_uat, get_uat
from tools.lark_cli import lark_cli

# Small config shims to support langgraph-style RunnableConfig for lark_cli.
class MockUser:
    def __init__(self, identity):
        self.identity = identity

class MockServerInfo:
    def __init__(self, open_id):
        self.user = MockUser(open_id)

class MockConfig:
    def __init__(self, open_id):
        self.server_info = MockServerInfo(open_id)

def handle_save_uat(args):
    try:
        scopes = [s.strip() for s in args.scopes.split(",") if s.strip()] if args.scopes else []
        save_uat(
            open_id=args.open_id,
            uat=args.uat,
            refresh_token=args.refresh_token,
            expires_at=args.expires_at,
            scopes=scopes,
            name=args.name or args.open_id
        )
        print(json.dumps({"ok": True}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)

def handle_chats(args):
    open_id = args.open_id
    token = get_uat(open_id)
    if not token:
        print(json.dumps({"ok": False, "error": "Unauthorized: Feishu token invalid or expired."}))
        sys.exit(1)
        
    try:
        command = "im +chat-list"
        config = MockConfig(open_id)
        cli_resp = lark_cli(command, config=config)
        if cli_resp.startswith("Error"):
            print(json.dumps({"ok": False, "error": cli_resp}))
            sys.exit(1)
            
        data = json.loads(cli_resp)
        chats_list = []
        chats = data.get("data", {}).get("chats") or []
        for item in chats:
            if item.get("chat_mode") == "group":
                chats_list.append({
                    "chat_id": item.get("chat_id"),
                    "name": item.get("name", "未命名群聊")
                })
        print(json.dumps({"ok": True, "chats": chats_list}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)

def handle_uat_status(args):
    token = get_uat(args.open_id)
    if token:
        print(json.dumps({"ok": True, "authorized": True}))
    else:
        print(json.dumps({
            "ok": True,
            "authorized": False,
            "error": "Feishu user authorization is missing or expired.",
        }))

def handle_sync(args):
    open_id = args.open_id
    title = args.title
    content = args.content
    
    token = get_uat(open_id)
    if not token:
        print(json.dumps({"ok": False, "error": "Unauthorized: Feishu token invalid or expired."}))
        sys.exit(1)
        
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID")
    if not app_token or not table_id:
        print(json.dumps({"ok": False, "error": "Bitable env vars FEISHU_BITABLE_APP_TOKEN or TABLE_ID not configured."}))
        sys.exit(1)
        
    try:
        config = MockConfig(open_id)
        title_field = os.environ.get("XHS_BITABLE_FIELD_TITLE", "标题")
        body_field = os.environ.get("XHS_BITABLE_FIELD_BODY", "正文内容")
        tags_field = os.environ.get("XHS_BITABLE_FIELD_TAGS", "标签")
        author_field = os.environ.get("XHS_BITABLE_FIELD_AUTHOR", "创建人")
        status_field = os.environ.get("XHS_BITABLE_FIELD_STATUS", "状态")
                
        fields_payload = {
            title_field: title,
            body_field: content,
            author_field: open_id,
            status_field: "草稿",
        }
        if getattr(args, "tags", None):
            fields_payload[tags_field] = args.tags

        create_payload = {"fields": fields_payload}

        sync_cmd = shlex.join([
            "base",
            "+record-create",
            "--base-token", app_token,
            "--table-id", table_id,
            "--json", json.dumps(create_payload, ensure_ascii=False)
        ])
        
        sync_resp = lark_cli(sync_cmd, config=config)
        if sync_resp.startswith("Error"):
            print(json.dumps({"ok": False, "error": f"Lark CLI error: {sync_resp}"}))
            sys.exit(1)
            
        try:
            res_data = json.loads(sync_resp)
            if "code" in res_data and res_data["code"] != 0:
                print(json.dumps({"ok": False, "error": res_data.get("msg", "Failed writing to Feishu Bitable.")}))
                sys.exit(1)
            record_id = (
                res_data.get("data", {}).get("record", {}).get("record_id")
                or res_data.get("data", {}).get("record_id")
                or ""
            )
        except Exception:
            record_id = ""
            
        print(json.dumps({
            "ok": True,
            "record_id": record_id,
            "redirect_url": f"https://feishu.cn/base/{app_token}?table={table_id}"
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)

def handle_notify(args):
    open_id = args.open_id
    chat_id = args.chat_id
    title = args.title
    content = args.content
    
    token = get_uat(open_id)
    if not token:
        print(json.dumps({"ok": False, "error": "Unauthorized: Feishu token invalid or expired."}))
        sys.exit(1)
        
    try:
        card_content = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🍠 小红书笔记待审核"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**选题标题**：\n{title}\n\n**笔记正文草稿**：\n{content}"
                    }
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "请前往小红书智能体文案工作台确认发布。"
                        }
                    ]
                }
            ]
        }
        
        notify_cmd = shlex.join([
            "im",
            "+messages-send",
            "--chat-id", chat_id,
            "--msg-type", "interactive",
            "--content", json.dumps(card_content)
        ])
        
        config = MockConfig(open_id)
        msg_resp = lark_cli(notify_cmd, config=config)
        
        if msg_resp.startswith("Error"):
            print(json.dumps({"ok": False, "error": msg_resp}))
            sys.exit(1)
            
        try:
            res_data = json.loads(msg_resp)
            if "code" in res_data and res_data["code"] != 0:
                print(json.dumps({"ok": False, "error": res_data.get("msg", "Failed sending card notification.")}))
                sys.exit(1)
        except Exception:
            pass
            
        print(json.dumps({"ok": True}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Feishu Web API bridge runner")
    parser.add_argument("--action", choices=["save-uat", "uat-status", "chats", "sync", "notify"], required=True)
    parser.add_argument("--open-id", required=True)
    parser.add_argument("--uat")
    parser.add_argument("--refresh-token")
    parser.add_argument("--expires-at", type=float)
    parser.add_argument("--scopes")
    parser.add_argument("--name")
    parser.add_argument("--record-id")
    parser.add_argument("--chat-id")
    parser.add_argument("--title")
    parser.add_argument("--content")
    parser.add_argument("--tags")
    parser.add_argument("--thread-id")
    
    args = parser.parse_args()
    
    if args.action == "save-uat":
        handle_save_uat(args)
    elif args.action == "uat-status":
        handle_uat_status(args)
    elif args.action == "chats":
        handle_chats(args)
    elif args.action == "sync":
        handle_sync(args)
    elif args.action == "notify":
        handle_notify(args)

if __name__ == "__main__":
    main()
