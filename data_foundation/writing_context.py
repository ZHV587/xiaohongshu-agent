"""账号/垂类写作上下文的统一值对象。"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping
import uuid


GLOBAL_SCOPE_KEY = "global"


@dataclass(frozen=True)
class WritingContext:
    account_id: str | None = None
    niche: str | None = None

    def __post_init__(self) -> None:
        account = normalize_account_id(self.account_id)
        niche = normalize_niche(self.niche)
        object.__setattr__(self, "account_id", account)
        object.__setattr__(self, "niche", niche)

    @property
    def is_global(self) -> bool:
        return self.account_id is None and self.niche is None

    @property
    def scope_key(self) -> str:
        if self.is_global:
            return GLOBAL_SCOPE_KEY
        return f"account={self.account_id or '*'};niche={self.niche or '*'}"

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "account_id": self.account_id,
            "niche": self.niche,
            "scope_key": self.scope_key,
        }


def context_from_state(state: Mapping[str, Any]) -> WritingContext:
    return WritingContext(
        account_id=state.get("current_account_id"),
        niche=state.get("current_niche"),
    )


def context_from_payload(payload: Any) -> WritingContext:
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        return WritingContext()
    try:
        return WritingContext(
            account_id=payload.get("account_id"),
            niche=payload.get("niche"),
        )
    except ValueError:
        return WritingContext()


def normalize_account_id(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return str(uuid.UUID(str(value).strip()))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("account_id must be a UUID") from exc


def normalize_niche(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if not cleaned:
        return None
    if len(cleaned) > 120:
        raise ValueError("niche must contain at most 120 characters")
    return cleaned.casefold()


__all__ = [
    "GLOBAL_SCOPE_KEY",
    "WritingContext",
    "context_from_payload",
    "context_from_state",
    "normalize_account_id",
    "normalize_niche",
]
