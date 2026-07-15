"""外部同步素材进入写作知识库前的确定性资格声明。

同步成功只说明数据搬运成功，不代表内容适合参与文案生成。本模块把来源配置、
表/空间白名单和正文完整度转换为可审计的 ``knowledge_qualification``，随后由
知识资格门机械校验；LLM 与同步状态都不能自行把素材升格为知识。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from data_foundation.feishu_metrics import NOTE_LEVEL_TABLE_IDS


XHS_COPYWRITING_DOMAIN = "xhs_copywriting"
MIN_SOURCE_CONTENT_CHARS = 20


def default_base_source_config(*, app_token: str, table_id: str) -> dict[str, Any]:
    """生产默认只允许已确认是笔记级事实的表进入知识库。"""

    configured = table_id.strip() if isinstance(table_id, str) else ""
    allowed = sorted(
        {
            *NOTE_LEVEL_TABLE_IDS,
            *([configured] if configured and configured != "configured-table" else []),
        }
    )
    return {
        "app_token": app_token or "configured-base",
        "table_id": configured or "configured-table",
        "knowledge_domain": XHS_COPYWRITING_DOMAIN,
        "knowledge_enabled": True,
        "knowledge_table_ids": allowed,
        "minimum_content_chars": MIN_SOURCE_CONTENT_CHARS,
    }


def default_wiki_source_config(*, wiki_space_id: str) -> dict[str, Any]:
    """配置的单一 Wiki 空间被显式声明为小红书写作知识域。"""

    return {
        "wiki_space_id": wiki_space_id or "configured-space",
        "knowledge_domain": XHS_COPYWRITING_DOMAIN,
        "knowledge_enabled": True,
        "minimum_content_chars": MIN_SOURCE_CONTENT_CHARS,
    }


def qualify_base_record(
    *,
    table_id: str,
    title: str,
    body: str,
    source_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    config = dict(source_config or {})
    allowed = _string_set(config.get("knowledge_table_ids"))
    # 直接调用同步函数（脚本/测试）没有 source config 时仍只认笔记级明文白名单。
    if not config:
        allowed = set(NOTE_LEVEL_TABLE_IDS)
    enabled = config.get("knowledge_enabled") is True if config else True
    domain = str(config.get("knowledge_domain") or XHS_COPYWRITING_DOMAIN).strip()
    minimum = _minimum_chars(config)
    content_chars = len((title + "\n" + body).strip())

    if not enabled:
        return _decision(False, "SOURCE_KNOWLEDGE_DISABLED", domain, content_chars)
    if domain != XHS_COPYWRITING_DOMAIN:
        return _decision(False, "SOURCE_DOMAIN_NOT_ALLOWED", domain, content_chars)
    if table_id not in allowed:
        return _decision(False, "BASE_TABLE_NOT_ALLOWLISTED", domain, content_chars)
    if content_chars < minimum or not body.strip():
        return _decision(False, "SOURCE_CONTENT_INCOMPLETE", domain, content_chars)
    return _decision(True, "EXPLICIT_SOURCE_ALLOWLIST", domain, content_chars)


def qualify_wiki_document(
    *,
    title: str,
    content: str,
    source_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    config = dict(source_config or {})
    domain = str(config.get("knowledge_domain") or "").strip()
    content_chars = len((title + "\n" + content).strip())
    if config.get("knowledge_enabled") is not True:
        return _decision(False, "SOURCE_KNOWLEDGE_DISABLED", domain, content_chars)
    if domain != XHS_COPYWRITING_DOMAIN:
        return _decision(False, "SOURCE_DOMAIN_NOT_ALLOWED", domain, content_chars)
    if content_chars < _minimum_chars(config) or not content.strip():
        return _decision(False, "SOURCE_CONTENT_INCOMPLETE", domain, content_chars)
    return _decision(True, "EXPLICIT_SOURCE_ALLOWLIST", domain, content_chars)


def is_explicitly_qualified(payload: Any) -> bool:
    return (
        isinstance(payload, Mapping)
        and payload.get("eligible") is True
        and payload.get("domain") == XHS_COPYWRITING_DOMAIN
        and payload.get("policy_version") == 1
    )


def _decision(
    eligible: bool, reason: str, domain: str, content_chars: int
) -> dict[str, Any]:
    return {
        "policy_version": 1,
        "eligible": eligible,
        "domain": domain or None,
        "reason": reason,
        "content_chars": max(int(content_chars), 0),
    }


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _minimum_chars(config: Mapping[str, Any]) -> int:
    try:
        value = int(config.get("minimum_content_chars", MIN_SOURCE_CONTENT_CHARS))
    except (TypeError, ValueError):
        value = MIN_SOURCE_CONTENT_CHARS
    return min(max(value, MIN_SOURCE_CONTENT_CHARS), 10_000)


__all__ = [
    "MIN_SOURCE_CONTENT_CHARS",
    "XHS_COPYWRITING_DOMAIN",
    "default_base_source_config",
    "default_wiki_source_config",
    "is_explicitly_qualified",
    "qualify_base_record",
    "qualify_wiki_document",
]
