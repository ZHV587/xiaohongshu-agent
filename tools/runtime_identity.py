from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeUser:
    identity: str


@dataclass(frozen=True)
class RuntimeServerInfo:
    user: RuntimeUser


@dataclass(frozen=True)
class RuntimeIdentityConfig:
    server_info: RuntimeServerInfo


def identity_config(open_id: str) -> RuntimeIdentityConfig:
    return RuntimeIdentityConfig(server_info=RuntimeServerInfo(user=RuntimeUser(identity=open_id)))


def actor_open_id_from_config(config: Any | None) -> str | None:
    if config is None:
        return None

    server_info = getattr(config, "server_info", None)
    user = getattr(server_info, "user", None) if server_info is not None else None
    identity = getattr(user, "identity", None) if user is not None else None
    if isinstance(identity, str) and identity.strip():
        return identity.strip()

    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
        identity = configurable.get("user_id") or configurable.get("open_id")
        if isinstance(identity, str) and identity.strip():
            return identity.strip()

    return None
