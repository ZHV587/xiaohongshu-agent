"""生成归因事实的清洗与摘要；不保存 Prompt 正文或用户私密原文。"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


PROMPT_CONTRACT_VERSION = "xhs-copywriting-2026-07-v2"


def digest_text(value: Any) -> str:
    text = value if isinstance(value, str) else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def latest_model_provenance(messages: Sequence[Any] | None) -> dict[str, str | None]:
    for message in reversed(list(messages or [])):
        metadata = getattr(message, "response_metadata", None)
        if not isinstance(metadata, Mapping):
            continue
        model_id = _text(metadata.get("xhs_model_id"))
        if model_id:
            return {
                "provider": _text(metadata.get("xhs_model_provider")) or None,
                "model_id": model_id,
                "gateway_name": _text(metadata.get("xhs_gateway_name")) or None,
            }
    return {"provider": None, "model_id": None, "gateway_name": None}


def safe_grounding_summary(grounding: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(grounding or {})
    evidence = []
    for item in source.get("evidence") or []:
        if not isinstance(item, Mapping):
            continue
        resource_id = _text(item.get("resource_id"))
        version = item.get("resource_version")
        if resource_id and isinstance(version, int) and not isinstance(version, bool) and version > 0:
            evidence.append({"resource_id": resource_id, "resource_version": version})
    return {
        "schema_version": 1,
        "query_digest": digest_text(source.get("query")),
        "retrieval_mode": source.get("retrieval_mode"),
        "evidence": evidence,
        "engines_used": list(source.get("engines_used") or []),
        "degraded_engines": list(source.get("degraded_engines") or []),
    }


def run_key(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "PROMPT_CONTRACT_VERSION",
    "digest_text",
    "latest_model_provenance",
    "run_key",
    "safe_grounding_summary",
]
