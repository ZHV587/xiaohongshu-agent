from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from data_foundation.feishu_metrics import extract_performance_metrics
from data_foundation.outbox_requests import default_write_requests
from data_foundation.performance_feedback import save_performance_metric_resource
from data_foundation.repositories.resource import ResourceRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    imported: int
    errors: list[str]


def _field_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _field_texts(item)]
    if isinstance(value, dict):
        result: list[str] = []
        for key in ("text", "name", "value", "label"):
            result.extend(_field_texts(value.get(key)))
        return result
    return []


def _field(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        values = _field_texts(fields.get(name))
        if values:
            return "\n".join(dict.fromkeys(values))
    return ""


def sync_base_rows(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    app_token: str,
    rows: list[dict[str, Any]],
) -> SyncResult:
    imported = 0
    errors: list[str] = []
    for row in rows:
        record_id = str(row.get("record_id") or "<missing>")
        # 每行带自己的来源 table_id(多表聚合);缺失时回退占位,保证 external_id 唯一。
        table_id = str(row.get("table_id") or "table")
        table_name = str(row.get("table_name") or "")
        external_id = f"{app_token}:{table_id}:{record_id}"
        identity_kind = str(row.get("identity_kind") or "feishu_record_id")
        external_type = "base_record" if identity_kind == "feishu_record_id" else "base_record_snapshot"
        try:
            if record_id == "<missing>":
                raise ValueError("record_id is required")
            fields = dict(row.get("fields") or {})
            title = _field(fields, ["标题", "选题", "title", "Title"]) or table_name or record_id
            body = _field(fields, ["正文", "正文内容", "视频文案", "评论内容", "文档内容", "content", "Content"])
            mapping = {
                "system": "feishu",
                "external_type": external_type,
                "external_id": external_id,
                "sync_status": "synced",
            }
            if row.get("external_updated_at") is not None:
                mapping["external_updated_at"] = row.get("external_updated_at")
            resource = repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_type="feishu_base_record",
                title=title,
                content_text=body,
                content_json={
                    "fields": fields,
                    "identity_kind": identity_kind,
                    "table_id": table_id,
                    "table_name": table_name,
                },
                visibility="team",
                owner_open_id=actor_open_id,
                mapping=mapping,
                outbox_requests=default_write_requests(),
            )
            imported += 1
            # 笔记级表的效果列接通:抽取 → 幂等写 performance_metric + measured_by。
            # 复用回填同一抽取/写入路径(单一事实源)。失败不阻断 base record 落库。
            metrics = extract_performance_metrics(table_id, table_name, fields)
            if metrics and resource is not None:
                try:
                    save_performance_metric_resource(
                        repo,
                        tenant_id=tenant_id,
                        actor_open_id=actor_open_id,
                        target_resource_id=resource.id,
                        metrics=metrics,
                        channel="xiaohongshu",
                    )
                except Exception as perf_exc:  # noqa: BLE001 - 不阻断 base record 落库
                    logger.warning(
                        "performance metric attach failed for %s: %s", external_id, perf_exc
                    )
        except Exception as exc:
            message = f"base_record {external_id}: {type(exc).__name__}: {exc}"
            logger.exception("Feishu Base sync failed for %s", external_id)
            repo.mark_mapping_failed(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                system="feishu",
                external_type=external_type,
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
            doc_mapping = {
                "system": "feishu",
                "external_type": "docx",
                "external_id": obj_token,
                "sync_status": "synced",
            }
            wiki_mapping = {
                "system": "feishu",
                "external_type": "wiki_node",
                "external_id": f"{space_id}:{node_token}",
                "sync_status": "synced",
            }
            if doc.get("external_updated_at") is not None:
                doc_mapping["external_updated_at"] = doc.get("external_updated_at")
                wiki_mapping["external_updated_at"] = doc.get("external_updated_at")
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
                    mapping=doc_mapping,
                    outbox_requests=default_write_requests(),
                )
                repo.upsert_mapping(
                    tenant_id=tenant_id,
                    resource_id=resource.id,
                    **wiki_mapping,
                )
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
