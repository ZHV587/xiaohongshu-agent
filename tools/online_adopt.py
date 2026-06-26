"""采纳收录工具:把用户选中的线上笔记一步写入 Postgres(权威)+ 同步飞书爆款采集库(镜像)。

单动作、幂等、数据库权威:
- 入库 + 接效果指标走 data_foundation 核心(按 redfox note_id 幂等)。
- 飞书镜像按 Postgres mapping(system="feishu_collect", external_id=note_id)幂等:已同步则跳过,
  避免重复行(用仅经验证的 lark-cli `+record-create` 能力)。
- 数据库先成功;飞书失败保留库记录并逐条报告,不回滚。
整工具纳入 agent `interrupt_on` → 飞书写经 HITL 人工确认(遵 README 架构铁律)。
"""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from data_foundation.db import connect
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.online_notes import (
    XHS_NOTE_EXTERNAL_TYPE,
    adopt_online_note_resource,
)
from tools.feishu_actions import create_online_note_record

FEISHU_COLLECT_SYSTEM = "feishu_collect"


@tool
def adopt_online_notes(
    notes: list[dict[str, Any]],
    sync_feishu: bool = True,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """采纳用户选中的线上笔记:写数据库(权威)+ 同步飞书爆款采集库(镜像)。幂等。

    Args:
        notes: 选中的线上笔记列表(卡片级字段,至少含 note_id/note_url)。
        sync_feishu: 是否同步飞书采集库(默认 True)。
    """
    if not isinstance(notes, list) or not notes:
        return {"ok": False, "error": "notes is required", "results": [], "errors": []}

    actor = actor_from_config(config)
    tenant_id = default_tenant_id()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    conn = connect()
    try:
        repo = ResourceRepository(conn)
        note_ids = [str(n.get("note_id") or "").strip() for n in notes if isinstance(n, dict)]
        already_synced = repo.existing_mapping_external_ids(
            tenant_id=tenant_id,
            system=FEISHU_COLLECT_SYSTEM,
            external_type=XHS_NOTE_EXTERNAL_TYPE,
            external_ids=note_ids,
        )

        for note in notes:
            if not isinstance(note, dict):
                errors.append({"note_id": "", "error": "note must be an object"})
                continue
            note_id = str(note.get("note_id") or "").strip()
            try:
                core = adopt_online_note_resource(
                    repo, tenant_id=tenant_id, actor_open_id=actor, note=note
                )
            except Exception as exc:  # noqa: BLE001 - 单条失败不影响其余
                errors.append({"note_id": note_id, "error": f"DB_ADOPT_FAILED: {exc}"})
                continue
            if not core.get("ok"):
                errors.append({"note_id": note_id, "error": core.get("error", "DB_ADOPT_FAILED")})
                continue

            resource_id = core["resource_id"]
            feishu_synced: bool | str = False
            if sync_feishu:
                if note_id in already_synced:
                    feishu_synced = "skipped"
                else:
                    fr = create_online_note_record(note, config=config)
                    if fr.get("ok"):
                        repo.upsert_mapping(
                            tenant_id=tenant_id,
                            resource_id=resource_id,
                            system=FEISHU_COLLECT_SYSTEM,
                            external_type=XHS_NOTE_EXTERNAL_TYPE,
                            external_id=note_id,
                            sync_status="synced",
                        )
                        feishu_synced = True
                    else:
                        feishu_synced = "failed"
                        errors.append({"note_id": note_id, "error": f"FEISHU_SYNC_FAILED: {fr.get('error')}"})

            results.append({
                "note_id": note_id,
                "adopted": True,
                "resource_id": resource_id,
                "feishu_synced": feishu_synced,
            })
    finally:
        conn.close()

    return {"ok": True, "results": results, "errors": errors}
