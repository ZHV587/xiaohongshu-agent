from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from data_foundation.repository import ResourceRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    imported: int
    errors: list[str]


def _field(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = fields.get(name)
        if value:
            return str(value)
    return ""


def sync_base_rows(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    app_token: str,
    table_id: str,
    rows: list[dict[str, Any]],
) -> SyncResult:
    imported = 0
    errors: list[str] = []
    for row in rows:
        record_id = str(row.get("record_id") or "<missing>")
        external_id = f"{app_token}:{table_id}:{record_id}"
        try:
            if record_id == "<missing>":
                raise ValueError("record_id is required")
            fields = dict(row.get("fields") or {})
            title = _field(fields, ["标题", "title", "Title"]) or record_id
            body = _field(fields, ["正文", "正文内容", "视频文案", "content", "Content"])
            repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_type="feishu_base_record",
                title=title,
                content_text=body,
                content_json={"fields": fields},
                visibility="team",
                owner_open_id=actor_open_id,
                mapping={
                    "system": "feishu",
                    "external_type": "base_record",
                    "external_id": external_id,
                    "sync_status": "synced",
                },
                outbox_topics=["meili_index", "embedding_generate", "graph_ingest"],
            )
            imported += 1
        except Exception as exc:
            message = f"base_record {external_id}: {type(exc).__name__}: {exc}"
            logger.exception("Feishu Base sync failed for %s", external_id)
            repo.mark_mapping_failed(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                system="feishu",
                external_type="base_record",
                external_id=external_id,
                error=message,
            )
            errors.append(message)
    return SyncResult(imported=imported, errors=errors)


def sync_wiki_documents(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    space_id: str,
    documents: list[dict[str, Any]],
) -> SyncResult:
    imported = 0
    errors: list[str] = []
    for doc in documents:
        obj_token = str(doc.get("obj_token") or "<missing>")
        node_token = str(doc.get("node_token") or "")
        try:
            if obj_token == "<missing>":
                raise ValueError("obj_token is required")
            if not node_token:
                raise ValueError("node_token is required")
            title = str(doc.get("title") or obj_token)
            content = str(doc.get("content") or "")
            with repo.unit_of_work():
                resource = repo.upsert_resource(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    resource_type="feishu_doc",
                    title=title,
                    content_text=content,
                    content_json={"space_id": space_id, "obj_token": obj_token, "node_token": node_token},
                    visibility="team",
                    owner_open_id=actor_open_id,
                    mapping={
                        "system": "feishu",
                        "external_type": "docx",
                        "external_id": obj_token,
                        "sync_status": "synced",
                    },
                    outbox_topics=["meili_index", "embedding_generate", "graph_ingest"],
                )
                repo.upsert_mapping(
                    tenant_id=tenant_id,
                    resource_id=resource.id,
                    system="feishu",
                    external_type="wiki_node",
                    external_id=f"{space_id}:{node_token}",
                    sync_status="synced",
                )
                chunks = [chunk.strip() for chunk in content.split("\n\n") if chunk.strip()]
                repo.replace_embedding_chunks(tenant_id=tenant_id, resource_id=resource.id, chunks=chunks)
            imported += 1
        except Exception as exc:
            message = f"wiki_doc {obj_token}: {type(exc).__name__}: {exc}"
            logger.exception("Feishu Wiki sync failed for %s", obj_token)
            repo.mark_mapping_failed(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                system="feishu",
                external_type="docx",
                external_id=obj_token,
                error=message,
            )
            if node_token:
                repo.mark_mapping_failed(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    system="feishu",
                    external_type="wiki_node",
                    external_id=f"{space_id}:{node_token}",
                    error=message,
                )
            errors.append(message)
    return SyncResult(imported=imported, errors=errors)
