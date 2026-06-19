from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

EDITABLE_KEYS = {
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_QUALITY_MODELS",
    "LLM_GATEWAY_2_BASE_URL",
    "LLM_GATEWAY_2_API_KEY",
    "LLM_GATEWAY_3_BASE_URL",
    "LLM_GATEWAY_3_API_KEY",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_BITABLE_APP_TOKEN",
    "FEISHU_BITABLE_TABLE_ID",
    "XHS_BITABLE_FIELD_TITLE",
    "XHS_BITABLE_FIELD_BODY",
    "XHS_BITABLE_FIELD_TAGS",
    "XHS_BITABLE_FIELD_AUTHOR",
    "XHS_BITABLE_FIELD_STATUS",
}

SECRET_KEYS = {
    "LLM_API_KEY",
    "LLM_GATEWAY_2_API_KEY",
    "LLM_GATEWAY_3_API_KEY",
    "FEISHU_APP_SECRET",
}

DEPLOY_ONLY_KEYS = {
    "XHS_ADMIN_OPEN_IDS",
    "XHS_JWT_SECRET",
    "XHS_INTERNAL_SECRET",
    "XHS_CONFIG_ENCRYPTION_KEY",
    "XHS_CONFIG_CENTER_PATH",
    "PATH",
    "NODE_OPTIONS",
}


class ConfigValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ConfigSnapshot:
    version: str
    values: dict[str, str]
    actor_open_id: str
    changed_keys: list[str]
    created_at: float


def _make_version(values: dict[str, str], created_at: float) -> str:
    digest = sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"{int(created_at)}-{digest}"


def _validate_updates(updates: dict[str, Any]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in updates.items():
        if key in DEPLOY_ONLY_KEYS or key not in EDITABLE_KEYS:
            raise ConfigValidationError(f"Config key is not editable: {key}")
        sanitized[key] = str(value or "")
    return sanitized


class ConfigCenter:
    def __init__(self, path: Path | str, encryption_key: str) -> None:
        self.path = Path(path)
        self.fernet = Fernet(encryption_key.encode("utf-8"))

    def _read_document(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"current": {}, "history": []}
        decrypted = self.fernet.decrypt(self.path.read_bytes())
        return json.loads(decrypted.decode("utf-8"))

    def _write_document(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.path.write_bytes(self.fernet.encrypt(payload))

    def save(self, actor_open_id: str, updates: dict[str, Any]) -> ConfigSnapshot:
        sanitized = _validate_updates(updates)
        document = self._read_document()
        current = {str(k): str(v) for k, v in document.get("current", {}).items()}
        next_values = {**current, **sanitized}
        created_at = time.time()
        snapshot = ConfigSnapshot(
            version=_make_version(next_values, created_at),
            values=next_values,
            actor_open_id=actor_open_id,
            changed_keys=sorted(sanitized),
            created_at=created_at,
        )
        history = list(document.get("history", []))
        history.append(
            {
                "version": snapshot.version,
                "values": snapshot.values,
                "actor_open_id": snapshot.actor_open_id,
                "changed_keys": snapshot.changed_keys,
                "created_at": snapshot.created_at,
            }
        )
        self._write_document({"current": next_values, "history": history})
        return snapshot

    def get_plain(self) -> dict[str, str]:
        return {str(k): str(v) for k, v in self._read_document().get("current", {}).items()}

    def get_redacted(self) -> dict[str, str]:
        plain = self.get_plain()
        return {key: ("********" if key in SECRET_KEYS and value else value) for key, value in plain.items()}

    def history(self) -> list[ConfigSnapshot]:
        items = self._read_document().get("history", [])
        return [
            ConfigSnapshot(
                version=item["version"],
                values={str(k): str(v) for k, v in item["values"].items()},
                actor_open_id=item["actor_open_id"],
                changed_keys=list(item["changed_keys"]),
                created_at=float(item["created_at"]),
            )
            for item in items
        ]


def bootstrap_snapshot_from_env(actor_open_id: str) -> ConfigSnapshot:
    values = {key: os.environ[key] for key in EDITABLE_KEYS if os.environ.get(key)}
    created_at = time.time()
    return ConfigSnapshot(
        version=_make_version(values, created_at),
        values=values,
        actor_open_id=actor_open_id,
        changed_keys=sorted(values),
        created_at=created_at,
    )


def default_config_center() -> ConfigCenter:
    key = os.environ["XHS_CONFIG_ENCRYPTION_KEY"]
    path = os.environ.get("XHS_CONFIG_CENTER_PATH", ".xhs-config/config-center.enc")
    return ConfigCenter(path=path, encryption_key=key)
