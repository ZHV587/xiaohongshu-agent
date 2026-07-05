"""采纳收录工具:把用户选中的线上笔记一步写入 Postgres(权威)+ 同步飞书爆款采集库(镜像)。

单动作、幂等、数据库权威:
- 入库 + 接效果指标走 data_foundation 核心(按 redfox note_id 幂等)。
- 飞书镜像按 Postgres mapping(system="feishu_collect", external_id=note_id)幂等:已同步则跳过,
  避免重复行(用仅经验证的 lark-cli `+record-create` 能力)。
- 数据库先成功;飞书失败保留库记录并逐条报告,不回滚。
整工具纳入 agent `interrupt_on` → 飞书写经 HITL 人工确认(遵 README 架构铁律)。
"""
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from data_foundation.db import connect
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.online_notes import (
    XHS_NOTE_EXTERNAL_TYPE,
    adopt_online_note_resource,
)
from data_foundation.creation_memory import associate_ingested_resource
from tools.feishu_actions import create_online_note_record

FEISHU_COLLECT_SYSTEM = "feishu_collect"


def _neighbor_query(note: dict[str, Any]) -> str:
    """从笔记的标题/摘要/标签拼一段检索文本,用于找语义/主题邻居(§0 关联)。"""
    parts: list[str] = []
    for key in ("title", "summary"):
        val = str(note.get(key) or "").strip()
        if val:
            parts.append(val)
    tags = note.get("tags")
    if isinstance(tags, list):
        parts.extend(str(t).strip() for t in tags if str(t).strip())
    return " ".join(parts).strip()


def _find_neighbors(query: str, config: RunnableConfig | None) -> list[dict[str, Any]]:
    """用全文检索(Meili,不依赖 embedding,永远可用)找已有素材作关联候选。

    只取 resource_id + score;检索失败/无命中返回空(由 associate_ingested_resource 退化到
    同批 co_ingested 兜底)。关联绝不能让采纳主流程失败,故此处吞掉一切异常。
    """
    try:
        # 延迟导入避免与 data_foundation.tools 的循环依赖(tools 层互相引用)。
        from data_foundation.tools import search_resources

        res = search_resources.func(query, limit=6, config=config)
    except Exception:  # noqa: BLE001 - 关联候选检索失败不影响采纳
        return []
    if not isinstance(res, dict) or not res.get("ok"):
        return []
    out: list[dict[str, Any]] = []
    for item in res.get("results", []) or []:
        if isinstance(item, dict) and item.get("resource_id"):
            out.append({"resource_id": item["resource_id"], "score": item.get("score")})
    return out


@tool
def adopt_online_notes(
    sync_feishu: bool = True,
    selected_notes: Annotated[
        list[dict[str, Any]] | None, InjectedState("selected_notes")
    ] = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """采纳用户在面板勾选的线上笔记:写数据库(权威)+ 同步飞书爆款采集库(镜像)。幂等。

    数据来源(官方 InjectedState,单一事实源):笔记由前端勾选时经 `submit` 直传 graph state
    `selected_notes`,**完全不经对话文本/LLM 转写**。你(模型)只需在用户触发采纳时调用本工具,
    **不传也无法传笔记内容**——直接 `adopt_online_notes()` 即可。

    Args:
        sync_feishu: 是否同步飞书采集库(默认 True)。
    """
    notes = selected_notes if isinstance(selected_notes, list) else None
    if not notes:
        return {
            "ok": False,
            "error": "no selected notes in state (前端未直传 selected_notes)",
            "results": [],
            "errors": [],
        }

    actor = actor_from_config(config)
    tenant_id = default_tenant_id()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    # (resource_id, note) 对:采纳成功后统一做 §0 关联(需全批 resource_id 才能挂同批兜底边)。
    adopted_pairs: list[tuple[str, dict[str, Any]]] = []

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
            adopted_pairs.append((resource_id, note))
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

        # ── §0 素材不孤立:每条采纳成功的笔记至少挂一条关联边(永不孤岛)。 ──
        # 全批采纳完再挂边:语义邻居用全文检索找已有素材;都没有时退化到同批 co_ingested。
        # 关联失败(检索挂了/建边报错)绝不影响采纳结果——逐条 try,把关联情况记进 result。
        all_ids = [rid for rid, _ in adopted_pairs]
        by_resource = {r["resource_id"]: r for r in results if r.get("resource_id")}
        for rid, note in adopted_pairs:
            try:
                neighbors = _find_neighbors(_neighbor_query(note), config)
                assoc = associate_ingested_resource(
                    repo,
                    tenant_id=tenant_id,
                    actor_open_id=actor,
                    resource_id=rid,
                    neighbors=neighbors,
                    co_ingested_ids=all_ids,
                )
                if rid in by_resource:
                    by_resource[rid]["associations"] = assoc
            except Exception as exc:  # noqa: BLE001 - 关联失败不影响采纳
                errors.append({"note_id": by_resource.get(rid, {}).get("note_id", ""),
                               "error": f"ASSOCIATION_FAILED: {exc}"})
    finally:
        conn.close()

    adopted_count = sum(1 for r in results if r.get("adopted"))
    next_step = (
        f"已收录 {adopted_count} 条到库(已进检索)。可基于这批 + 本地相关内容出选题:"
        "按 topic-content 流程检索取证后产出带 resource_id 依据的选题卡。"
        if adopted_count
        else None
    )
    return {"ok": True, "results": results, "errors": errors, "next_step": next_step}
