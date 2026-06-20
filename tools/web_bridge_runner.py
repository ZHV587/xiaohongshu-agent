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
from tools.runtime_identity import identity_config
from config_center import ConfigCenter

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
        config = identity_config(open_id)
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

def handle_config_status(args):
    center = ConfigCenter(path=args.config_path, encryption_key=args.encryption_key)
    history = center.history()
    version = history[-1].version if history else ""
    print(json.dumps({"ok": True, "configs": center.get_plain(), "version": version}, ensure_ascii=False))


def handle_config_set(args):
    try:
        updates = json.loads(args.configs or "{}")
        if not isinstance(updates, dict):
            raise ValueError("configs must be a JSON object")
        center = ConfigCenter(path=args.config_path, encryption_key=args.encryption_key)
        snapshot = center.save(actor_open_id=args.open_id or "system", updates=updates)
        print(json.dumps({
            "ok": True,
            "version": snapshot.version,
            "changed_keys": snapshot.changed_keys,
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)


def handle_wiki_space(args):
    open_id = args.open_id
    token = get_uat(open_id)
    fallback_space_id = os.environ.get("FEISHU_WIKI_SPACE_ID", "7648177996175543260")
    if not token:
        print(json.dumps({"ok": True, "name": "小红书爆单手册", "space_id": fallback_space_id}, ensure_ascii=False))
        return
        
    try:
        config = identity_config(open_id)
        cmd = shlex.join(["wiki", "spaces", "get", "--space-id", fallback_space_id])
        cli_resp = lark_cli(cmd, config=config)
        
        if cli_resp.startswith("Error") or "error" in cli_resp.lower() or cli_resp.startswith("⚠️"):
            # Fallback if API fails or scope missing
            print(json.dumps({"ok": True, "name": "小红书爆单手册", "space_id": fallback_space_id}, ensure_ascii=False))
            return
            
        data = json.loads(cli_resp)
        space_name = data.get("data", {}).get("space", {}).get("name") or "小红书爆单手册"
        print(json.dumps({"ok": True, "name": space_name, "space_id": fallback_space_id}, ensure_ascii=False))
    except Exception:
        print(json.dumps({"ok": True, "name": "小红书爆单手册", "space_id": fallback_space_id}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Feishu Web API bridge runner")
    parser.add_argument(
        "--action",
        choices=["save-uat", "uat-status", "chats", "config-status", "config-set", "wiki-space"],
        required=True,
    )
    parser.add_argument("--open-id", required=False)
    parser.add_argument("--uat")
    parser.add_argument("--refresh-token")
    parser.add_argument("--expires-at", type=float)
    parser.add_argument("--scopes")
    parser.add_argument("--name")
    parser.add_argument("--config-path")
    parser.add_argument("--encryption-key")
    parser.add_argument("--configs")
    
    args = parser.parse_args()
    
    if args.action == "save-uat":
        handle_save_uat(args)
    elif args.action == "uat-status":
        handle_uat_status(args)
    elif args.action == "chats":
        handle_chats(args)
    elif args.action == "config-status":
        handle_config_status(args)
    elif args.action == "config-set":
        handle_config_set(args)
    elif args.action == "wiki-space":
        handle_wiki_space(args)

if __name__ == "__main__":
    main()
