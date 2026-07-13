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
    find_adopted_note_ids,
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


def _find_neighbors(
    repo: ResourceRepository,
    *,
    query: str,
    tenant_id: str,
    actor_open_id: str,
) -> list[dict[str, Any]]:
    """通过统一检索领域服务找已有素材作关联候选。

    只取精确身份与分数；候选已通过当前知识门和 ACL。检索失败或无命中返回空，由
    ``associate_ingested_resource`` 使用同批弱关联兜底。关联不能阻断采纳主流程。
    """
    try:
        from data_foundation.retrieval import retrieve_for_actor

        package = retrieve_for_actor(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            query=query,
            limit=6,
        )
    except Exception:  # noqa: BLE001 - 关联候选检索失败不影响采纳
        return []
    return [
        {
            "resource_id": item.resource_id,
            "resource_version": item.resource_version,
            "score": item.score,
        }
        for item in package.evidence
    ]


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
    adopted_pairs: list[tuple[str, int, dict[str, Any]]] = []

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
        # 采纳前先探这批里哪些已在库(redfox mapping 已存在)——upsert 幂等,重复采纳不会新建,
        # 但对用户是「跳过」(库里早有)而非「新收录」。前端据此把结果拆成 成功/跳过/失败 三态,
        # 忠实反映本次真实动作,不把已有的当成新入库邀功。
        already_adopted = find_adopted_note_ids(
            repo, tenant_id=tenant_id, note_ids=note_ids
        )

        for note in notes:
            if not isinstance(note, dict):
                errors.append({"note_id": "", "error": "note must be an object"})
                continue
            note_id = str(note.get("note_id") or "").strip()
            # 标题随成功/失败行一并回带,供前端结果弹窗逐条辨识「哪篇」;缺标题兜底为 note_id。
            note_title = str(note.get("title") or "").strip() or note_id
            try:
                core = adopt_online_note_resource(
                    repo, tenant_id=tenant_id, actor_open_id=actor, note=note
                )
            except Exception as exc:  # noqa: BLE001 - 单条失败不影响其余
                errors.append({"note_id": note_id, "title": note_title, "error": f"DB_ADOPT_FAILED: {exc}"})
                continue
            if not core.get("ok"):
                errors.append({"note_id": note_id, "title": note_title, "error": core.get("error", "DB_ADOPT_FAILED")})
                continue

            resource_id = core["resource_id"]
            resource_version = int(core["resource_version"])
            adopted_pairs.append((resource_id, resource_version, note))
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
                # 标题随结果回带,供前端结果弹窗逐条列出「哪篇入库/哪篇失败」而不必回查素材栏
                # (失败项通常已不在素材栏或用户已切走)。
                "title": note_title,
                "adopted": True,
                # already_adopted=True 表示本次采纳前库里就有(幂等 upsert,非本次新收录)→ 前端计「跳过」。
                "already_adopted": note_id in already_adopted,
                "resource_id": resource_id,
                "resource_version": resource_version,
                "feishu_synced": feishu_synced,
            })

        # ── §0 素材不孤立:每条采纳成功的笔记至少挂一条关联边(永不孤岛)。 ──
        # 全批采纳完再挂边:语义邻居用全文检索找已有素材;都没有时退化到同批 co_ingested。
        # 关联失败(检索挂了/建边报错)绝不影响采纳结果——逐条 try,把关联情况记进 result。
        all_resources = [
            {"resource_id": rid, "resource_version": version}
            for rid, version, _ in adopted_pairs
        ]
        by_resource = {r["resource_id"]: r for r in results if r.get("resource_id")}
        for rid, resource_version, note in adopted_pairs:
            try:
                neighbors = _find_neighbors(
                    repo,
                    query=_neighbor_query(note),
                    tenant_id=tenant_id,
                    actor_open_id=actor,
                )
                assoc = associate_ingested_resource(
                    repo,
                    tenant_id=tenant_id,
                    actor_open_id=actor,
                    resource_id=rid,
                    resource_version=resource_version,
                    neighbors=neighbors,
                    co_ingested_resources=all_resources,
                )
                if rid in by_resource:
                    by_resource[rid]["associations"] = assoc
            except Exception as exc:  # noqa: BLE001 - 关联失败不影响采纳
                errors.append({"note_id": by_resource.get(rid, {}).get("note_id", ""),
                               "error": f"ASSOCIATION_FAILED: {exc}"})
    finally:
        conn.close()

    adopted_count = sum(1 for r in results if r.get("adopted"))
    # 拆「本次新收录」与「库里早有(跳过)」两个计数,供 next_step 如实叙述,不把已有的当新入库邀功。
    skipped_count = sum(1 for r in results if r.get("adopted") and r.get("already_adopted"))
    new_count = adopted_count - skipped_count
    next_step = (
        f"已收录 {adopted_count} 条到库"
        + (f"(其中 {new_count} 条新入库、{skipped_count} 条库里早有)" if skipped_count else "")
        + "(均已进入知识治理)。可基于这批 + 本地相关内容出选题:"
        "按 topic-content 流程检索取证后产出带 resource_id 依据的选题卡。"
        if adopted_count
        else None
    )
    return {"ok": True, "results": results, "errors": errors, "next_step": next_step}
