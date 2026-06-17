# tools/internal_server.py
import os
import json
import hmac
import hashlib
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from tools.uat_store import save_uat

logger = logging.getLogger(__name__)

class InternalUATHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging raw requests to clean stdout
        pass

    def do_POST(self):
        if self.path != "/_internal/uat":
            self.send_response(404)
            self.end_headers()
            return

        # 1) HMAC authentication check
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("HMAC "):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized: Missing HMAC signature.")
            return
            
        client_sig = auth_header[5:].strip()
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        jwt_secret = os.environ.get("XHS_JWT_SECRET", "")
        if not jwt_secret:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Internal server misconfiguration: missing secret.")
            return

        try:
            payload = json.loads(body.decode("utf-8"))
            open_id = payload["open_id"]
            uat = payload["uat"]
            refresh_token = payload["refresh_token"]
            expires_at = int(payload["expires_at"])
            scopes = payload.get("scopes", [])
            name = payload.get("name", "")
            
            # Reconstruct signature base exactly matching TypeScript's format
            sign_text = f"{open_id}:{uat}:{refresh_token}:{expires_at}"
            expected_sig = hmac.new(
                jwt_secret.encode("utf-8"),
                sign_text.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Bad Request: Failed to parse body or construct signature: {e}".encode("utf-8"))
            return

        if not hmac.compare_digest(expected_sig, client_sig):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Signature validation failed.")
            return

        # 2) Save UAT
        try:
            save_uat(open_id, uat, refresh_token, expires_at, scopes, name)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
        except Exception as e:
            logger.error(f"Error saving UAT: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

def start_internal_server():
    port = int(os.environ.get("XHS_INTERNAL_PORT", 8081))
    try:
        server = HTTPServer(("127.0.0.1", port), InternalUATHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Started local internal UAT synchronization HTTP server on 127.0.0.1:{port}")
        return server
    except OSError as e:
        logger.error(f"Failed to start internal UAT HTTP server on port {port}: {e}. Next.js OAuth callbacks will not sync UAT tokens.")
        return None
