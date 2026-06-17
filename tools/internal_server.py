# tools/internal_server.py
import os
import json
import hmac
import hashlib
import time
import logging
import threading
import httpx
import shlex
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from tools.uat_store import save_uat, get_uat
from tools.lark_cli import lark_cli

logger = logging.getLogger(__name__)

# Mock classes to support langgraph style RunnableConfig for lark_cli
class MockUser:
    def __init__(self, identity):
        self.identity = identity

class MockServerInfo:
    def __init__(self, open_id):
        self.user = MockUser(open_id)

class MockConfig:
    def __init__(self, open_id):
        self.server_info = MockServerInfo(open_id)

# Max body size: 5MB to prevent OOM / DoS
MAX_PAYLOAD_SIZE = 5 * 1024 * 1024

# Isolated client instance for Feishu API calls, so tests can patch it cleanly
_feishu_client = httpx.Client()

class InternalUATHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging raw requests to clean stdout
        pass

    def _send_response_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_error(self, status_code: int, message: str):
        self.send_response(status_code)
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))

    def _verify_hmac(self, sign_text: str) -> bool:
        """Helper to verify incoming HMAC signature from Next.js proxy."""
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("HMAC "):
            return False
        
        client_sig = auth_header[5:].strip()
        jwt_secret = os.environ.get("XHS_JWT_SECRET", "")
        if not jwt_secret:
            logger.error("Internal UAT server missing XHS_JWT_SECRET.")
            return False

        expected_sig = hmac.new(
            jwt_secret.encode("utf-8"),
            sign_text.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_sig, client_sig)

    def _read_body(self) -> bytes | None:
        """Reads body with max payload size safety checks."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > MAX_PAYLOAD_SIZE:
            self._send_response_json(413, {"error": "Payload Too Large"})
            return None
        return self.rfile.read(content_length)

    def do_GET(self):
        # 1) Endpoint: /_internal/status (Checks system health/modes)
        if self.path == "/_internal/status":
            app_id = os.environ.get("FEISHU_APP_ID", "")
            app_secret = os.environ.get("FEISHU_APP_SECRET", "")
            has_bot = bool(app_id and app_secret)
            self._send_response_json(200, {
                "ok": True,
                "bot_configured": has_bot,
                "internal_port": int(os.environ.get("XHS_INTERNAL_PORT", 8081))
            })
            return

        # 2) Endpoint: /_internal/chats (Retrieve authorized user groups)
        if self.path.startswith("/_internal/chats"):
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("HMAC "):
                self._send_error(401, "Unauthorized: Missing HMAC signature.")
                return

            open_id = self.headers.get("X-Open-ID", "").strip()
            timestamp_str = self.headers.get("X-Timestamp", "").strip()
            
            if not open_id or not timestamp_str:
                self._send_error(400, "Bad Request: Missing X-Open-ID or X-Timestamp headers.")
                return

            # Prevent replay attacks: timestamp must be within 5 minutes
            try:
                timestamp = int(timestamp_str)
                if abs(time.time() - timestamp) > 300:
                    self._send_error(403, "Forbidden: Timestamp expired/replay detected.")
                    return
            except ValueError:
                self._send_error(400, "Bad Request: Invalid timestamp format.")
                return

            # Verify HMAC signature bound to open_id and timestamp
            sign_text = f"{open_id}:{timestamp}"
            if not self._verify_hmac(sign_text):
                self._send_error(403, "Forbidden: Signature validation failed.")
                return

            # Fetch token
            token = get_uat(open_id)
            if not token:
                self._send_response_json(401, {"error": "Unauthorized: Feishu token invalid or expired."})
                return

            # Call Lark CLI to get user chats/groups list
            try:
                command = "im +chat-list"
                config = MockConfig(open_id)
                cli_resp = lark_cli.func(command, config=config)
                if cli_resp.startswith("Error"):
                    logger.error(f"Lark CLI chats error: {cli_resp}")
                    self._send_response_json(500, {"error": cli_resp})
                    return
                
                try:
                    data = json.loads(cli_resp)
                except Exception as e:
                    logger.error(f"Failed to parse Lark CLI response: {cli_resp}. Error: {e}")
                    self._send_response_json(500, {"error": "Invalid JSON response from Lark CLI"})
                    return
                
                # Filter to only return actual groups, omitting single chats
                chats_list = []
                items = []
                if "items" in data:
                    items = data["items"]
                elif "data" in data and "items" in data["data"]:
                    items = data["data"]["items"]

                for item in items:
                    if item.get("chat_mode") == "group":
                        chats_list.append({
                            "chat_id": item.get("chat_id"),
                            "name": item.get("name", "未命名群聊")
                        })
                
                self._send_response_json(200, {"ok": True, "chats": chats_list})
            except Exception as e:
                logger.error(f"Exception fetching chats via Lark CLI: {e}")
                self._send_response_json(500, {"error": str(e)})
            return

        self._send_error(404, "Not Found")

    def do_POST(self):
        # Early Authorization Header validation for all POST endpoints
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("HMAC "):
            self._send_error(401, "Unauthorized: Missing HMAC signature.")
            return

        # 1) Endpoint: /_internal/uat (Save/Sync UAT)
        if self.path == "/_internal/uat":
            body = self._read_body()
            if body is None:
                return

            try:
                payload = json.loads(body.decode("utf-8"))
                open_id = payload["open_id"]
                uat = payload["uat"]
                refresh_token = payload["refresh_token"]
                expires_at = int(payload["expires_at"])
                scopes = payload.get("scopes", [])
                name = payload.get("name", "")
                
                sign_text = f"{open_id}:{uat}:{refresh_token}:{expires_at}"
                if not self._verify_hmac(sign_text):
                    self._send_error(403, "Forbidden: Signature validation failed.")
                    return

                save_uat(open_id, uat, refresh_token, expires_at, scopes, name)
                self._send_response_json(200, {"ok": True})
            except Exception as e:
                self._send_error(400, f"Bad Request: {e}")
            return

        # 2) Endpoint: /_internal/sync (Synchronize notes to Bitable with fuzzy matching)
        if self.path == "/_internal/sync":
            body = self._read_body()
            if body is None:
                return

            try:
                payload = json.loads(body.decode("utf-8"))
                open_id = payload["open_id"]
                record_id = payload["recordId"]
                title = payload["title"]
                content = payload["content"]
                timestamp = int(payload["timestamp"])

                # Anti-replay check
                if abs(time.time() - timestamp) > 300:
                    self._send_error(403, "Forbidden: Timestamp expired/replay detected.")
                    return

                # Signature bound to load hash + recordId + timestamp
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                sign_text = f"{open_id}:{record_id}:{content_hash}:{timestamp}"
                if not self._verify_hmac(sign_text):
                    self._send_error(403, "Forbidden: Signature validation failed.")
                    return

                token = get_uat(open_id)
                if not token:
                    self._send_response_json(401, {"error": "Unauthorized: User token invalid. Please log in again."})
                    return

                app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
                table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID", "")
                if not app_token or not table_id:
                    self._send_response_json(500, {"error": "Misconfigured environment variables for Bitable."})
                    return

                # Perform dynamic column fuzzy matching via Lark CLI
                field_cmd = shlex.join([
                    "base",
                    "+field-list",
                    "--base-token", app_token,
                    "--table-id", table_id
                ])
                config = MockConfig(open_id)
                cli_fields_resp = lark_cli.func(field_cmd, config=config)
                
                body_field = "正文内容"  # Fallbacks
                title_field = "标题"

                if not cli_fields_resp.startswith("Error"):
                    try:
                        fields_data = json.loads(cli_fields_resp)
                        items = []
                        if "items" in fields_data:
                            items = fields_data["items"]
                        elif "data" in fields_data and "items" in fields_data["data"]:
                            items = fields_data["data"]["items"]
                            
                        found_body = None
                        found_title = None
                        
                        # Fuzzy match heuristics for body and title text fields
                        for f in items:
                            fname = f.get("field_name", "")
                            
                            # Match body text column
                            if any(kw in fname for kw in ["正文", "内容", "文案", "主正文", "Body", "Content"]):
                                found_body = f.get("field_id", fname)
                            # Match title column
                            if any(kw in fname for kw in ["标题", "主题", "Title", "Subject"]):
                                found_title = f.get("field_id", fname)
                                
                        if found_body:
                            body_field = found_body
                        if found_title:
                            title_field = found_title
                    except Exception as e:
                        logger.warning(f"Failed to parse Bitable fields JSON: {e}")

                # Construct update fields object
                fields_payload = {
                    body_field: content,
                    title_field: title
                }

                # Update row record via Lark CLI +record-batch-update
                update_payload = {
                    "record_id_list": [record_id],
                    "patch": fields_payload
                }
                sync_cmd = shlex.join([
                    "base",
                    "+record-batch-update",
                    "--base-token", app_token,
                    "--table-id", table_id,
                    "--json", json.dumps(update_payload)
                ])
                
                sync_resp = lark_cli.func(sync_cmd, config=config)
                if sync_resp.startswith("Error"):
                    logger.error(f"Failed to update Bitable record via CLI: {sync_resp}")
                    self._send_response_json(500, {"error": f"Failed updating record: {sync_resp}"})
                    return
                
                try:
                    res_data = json.loads(sync_resp)
                    if "code" in res_data and res_data["code"] != 0:
                        self._send_response_json(500, {"error": res_data.get("msg", "Failed writing to Feishu table.")})
                        return
                except Exception:
                    pass

                self._send_response_json(200, {"ok": True})
            except Exception as e:
                logger.error(f"Exception during sync processing: {e}")
                self._send_response_json(500, {"error": str(e)})
            return

        # 3) Endpoint: /_internal/notify (Send rich message card to Feishu group)
        if self.path == "/_internal/notify":
            body = self._read_body()
            if body is None:
                return

            try:
                payload = json.loads(body.decode("utf-8"))
                open_id = payload["open_id"]
                chat_id = payload["chatId"]
                title = payload["title"]
                content = payload["content"]
                timestamp = int(payload["timestamp"])

                # Anti-replay check
                if abs(time.time() - timestamp) > 300:
                    self._send_error(403, "Forbidden: Timestamp expired/replay detected.")
                    return

                # Signature verification
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                sign_text = f"{open_id}:{chat_id}:{content_hash}:{timestamp}"
                if not self._verify_hmac(sign_text):
                    self._send_error(403, "Forbidden: Signature validation failed.")
                    return

                token = get_uat(open_id)
                if not token:
                    self._send_response_json(401, {"error": "Unauthorized: User token invalid."})
                    return

                # Build elegant Feishu Message Card (interactive)
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

                # Call Lark CLI to send interactive card message
                notify_cmd = shlex.join([
                    "im",
                    "+messages-send",
                    "--chat-id", chat_id,
                    "--msg-type", "interactive",
                    "--content", json.dumps(card_content)
                ])
                
                config = MockConfig(open_id)
                msg_resp = lark_cli.func(notify_cmd, config=config)
                
                if msg_resp.startswith("Error"):
                    logger.error(f"Failed sending Feishu card message via CLI: {msg_resp}")
                    self._send_response_json(500, {"error": f"Lark CLI returned error: {msg_resp}"})
                    return

                try:
                    res_data = json.loads(msg_resp)
                    if "code" in res_data and res_data["code"] != 0:
                        self._send_response_json(500, {"error": res_data.get("msg", "Failed sending card notification.")})
                        return
                except Exception:
                    pass

                self._send_response_json(200, {"ok": True})
            except Exception as e:
                logger.error(f"Exception during notification delivery: {e}")
                self._send_response_json(500, {"error": str(e)})
            return

        self._send_error(404, "Not Found")

def start_internal_server():
    port = int(os.environ.get("XHS_INTERNAL_PORT", 8081))
    try:
        # Use ThreadingHTTPServer for full asynchronous concurrency handling
        server = ThreadingHTTPServer(("127.0.0.1", port), InternalUATHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Started local multi-threaded internal UAT/Sync HTTP server on 127.0.0.1:{port}")
        return server
    except OSError as e:
        logger.error(f"Failed to start internal UAT HTTP server on port {port}: {e}. Sync features will be offline.")
        return None
