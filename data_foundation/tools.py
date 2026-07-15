from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState

from data_foundation.creation_memory import (
    save_generated_copy_resource,
    save_generated_topic_resource,
    save_user_feedback_resource,
)
from data_foundation import operations as ops
from data_foundation.outbox_requests import default_write_requests
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.studio_shared import is_admin_open_id, repository as _repository
from data_foundation.performance_feedback import (
    get_resource_performance_payload,
    save_performance_metric_resource,
)
from data_foundation.retrieval_contract import retrieval_error
from data_foundation.source_repository import SourceRepository
from data_foundation.sync_service import sync_feishu_sources
from data_foundation.writing_teardown import save_writing_teardown_resource


logger = logging.getLogger(__name__)


@tool
def search_local_note_cards(keyword: str, limit: int = 12, config: RunnableConfig = None) -> dict[str, Any]:
    """检索本地已收录笔记，返回发现面板所需的封面、互动和标签卡片。

    本工具是独立的素材发现入口；统一知识证据只由 ``retrieve_knowledge`` 返回。
    """
    actor = actor_from_config(config)
    from data_foundation.engine_config import meili_config_from_env
    from data_foundation.meili_client import MeiliResourceIndex
    from data_foundation.local_cards import dedupe_by_note_url, hydrate_note_card

    cfg = meili_config_from_env()
    if cfg.state != "enabled":
        return {"ok": False, "error": "MEILI_UNAVAILABLE", "results": []}
    want = min(max(int(limit), 1), 30)
    over_fetch = min(want * 5, 200)
    try:
        index = MeiliResourceIndex.from_config(cfg)
        hits = index.search(keyword.strip(), tenant_id=default_tenant_id(), limit=over_fetch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("local note card search failed: %s", type(exc).__name__)
        return {"ok": False, "error": "MEILI_QUERY_FAILED", "results": []}
    ids = [hit.resource_id for hit in hits]
    versions = [hit.resource_version for hit in hits]
    score_by_identity = {
        (hit.resource_id, hit.resource_version): hit.score for hit in hits
    }
    with _repository() as repo:
        rows = repo.readable_rows_by_ids(
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_ids=ids,
            resource_versions=versions,
        )
    cards: list[dict[str, Any]] = []
    for row in rows:
        content_json = dict(row["content_json"]) if row.get("content_json") is not None else {}
        card = hydrate_note_card(
            str(row["id"]),
            int(row["resource_version"]),
            row["type"],
            content_json,
            score=score_by_identity.get(
                (str(row["id"]), int(row["resource_version"])), 0.0
            ),
        )
        if card is not None:
            cards.append(card)
    cards = dedupe_by_note_url(cards)
    return {"ok": True, "results": cards[:want]}


@tool
def retrieve_knowledge(
    query: str,
    limit: int = 10,
    filters: dict[str, Any] | None = None,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """统一检索当前可用的知识证据。

    内部融合 pgvector、Meilisearch 与 FalkorDB，但所有候选都必须经过 PostgreSQL
    当前知识指针、精确版本、租户和 ACL 裁决。返回的 ``resource_id`` 与
    ``resource_version`` 必须成对传给 ``get_resource``，不得猜测最新版本。
    """
    actor = actor_from_config(config)
    from pydantic import ValidationError

    from data_foundation.evidence import RetrievalFilters
    from data_foundation.retrieval import (
        RetrievalSecurityGateError,
        retrieve_for_actor,
    )

    try:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query is required")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("limit must be an integer")
        selected_filters = RetrievalFilters.model_validate(filters or {})
    except (TypeError, ValueError, ValidationError):
        return retrieval_error("INVALID_RETRIEVAL_REQUEST")

    try:
        with _repository() as repo:
            package = retrieve_for_actor(
                repo,
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                query=query,
                limit=limit,
                filters=selected_filters,
            )
    except RetrievalSecurityGateError:
        return retrieval_error("POSTGRES_KNOWLEDGE_GATE_FAILED")
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge retrieval failed: %s", type(exc).__name__)
        return retrieval_error("KNOWLEDGE_RETRIEVAL_FAILED")
    return package.model_dump(mode="json")


@tool
def get_resource(
    resource_id: str,
    resource_version: int,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Read one exact resource snapshot after tenant and permission filtering.

    Both ``resource_id`` and ``resource_version`` must come from the same search or
    graph result.  The tool never guesses a latest or knowledge-pointer version.
    """
    actor = actor_from_config(config)
    if (
        not isinstance(resource_version, int)
        or isinstance(resource_version, bool)
        or resource_version <= 0
    ):
        raise ValueError("resource_version must be a positive integer")
    # resources.id 是 uuid 列,where r.id=%s 对非 UUID 串会抛 22P02 invalid uuid 并冒泡。
    # LLM 常传幻觉 id/标题(如 "generated-1"),按契约应返回 not found 而非把 SQL 错误回给模型。
    try:
        uuid.UUID(str(resource_id))
    except (ValueError, TypeError, AttributeError):
        return {"ok": False, "error": "Resource not found or not permitted"}
    with _repository() as repo:
        resource = repo.get_resource_for_knowledge(
            default_tenant_id(), actor, resource_id, resource_version
        )
    if resource is None:
        return {"ok": False, "error": "Resource not found or not permitted"}
    return {
        "ok": True,
        "resource": {
            "resource_id": resource.id,
            "type": resource.type,
            "title": resource.title,
            "summary": resource.summary,
            "content_text": resource.content_text,
            "content_json": resource.content_json,
            "version": resource.version,
            "source_updated_at": (
                resource.source_updated_at.isoformat() if resource.source_updated_at else None
            ),
            "indexed_at": resource.updated_at.isoformat() if resource.updated_at else None,
        },
    }


@tool
def get_generated_copy_lifecycle(
    resource_id: str,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Read exact generated-copy snapshots and current CAS tokens for a revision.

    Use this before ``save_generated_copy`` when an existing resource's
    ``latest_resource_version`` or ``state_version`` is absent/stale.  Access requires
    owner/write permission; candidate bodies are returned only to that editor path and
    are not exposed through the general knowledge retrieval tool.
    """
    actor = actor_from_config(config)
    try:
        uuid.UUID(str(resource_id))
    except (ValueError, TypeError, AttributeError):
        return {"ok": False, "error": "Generated copy not found or not permitted"}
    from data_foundation.repositories.generated_copy import GeneratedCopyRepository

    try:
        with _repository() as repo:
            lifecycle = GeneratedCopyRepository(repo)
            state = lifecycle.get_state(
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                resource_id=resource_id,
            )
            snapshots = lifecycle.list_versions(
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                resource_id=resource_id,
            )
    except (PermissionError, ValueError):
        return {"ok": False, "error": "Generated copy not found or not permitted"}
    return {
        "ok": True,
        "lifecycle": {
            "resource_id": state.resource_id,
            "status": state.lifecycle_status,
            "selected_version": state.selected_version,
            "selected_label": state.selected_label,
            "adopted_version": state.adopted_version,
            "finalized_version": state.finalized_version,
            "published_version": state.published_version,
            "knowledge_target_version": state.knowledge_target_version,
            "latest_resource_version": state.latest_resource_version,
            "state_version": state.state_version,
            "versions": [
                {
                    "resource_version": snapshot["resourceVersion"],
                    "label": snapshot["label"],
                    "title": snapshot["title"],
                    "body": snapshot["body"],
                    "tags": snapshot["tags"],
                    "cover": snapshot["cover"],
                    "note": snapshot["note"],
                }
                for snapshot in snapshots
            ],
        },
    }


@tool
def get_writing_profile(config: RunnableConfig = None) -> dict[str, Any]:
    """Read the current actor's exact private writing-preference profile.

    The profile is loaded through ``writing_profile_states`` rather than general
    knowledge retrieval, so another user's private observations can never enter the
    result and an outdated resource snapshot is never guessed from ``resources``.
    """
    actor = actor_from_config(config)
    from data_foundation.preference_learning import PreferenceLearningService

    with _repository() as repo:
        return PreferenceLearningService(repo).get_profile(
            tenant_id=default_tenant_id(), actor_open_id=actor
        )


@tool
def get_data_foundation_status(config: RunnableConfig = None) -> dict[str, Any]:
    """Return Postgres data foundation resource, sync, and outbox status."""
    actor_from_config(config)
    with _repository() as repo:
        status = repo.data_foundation_status(default_tenant_id())
    return {"ok": True, "status": status}


@tool
def sync_feishu_resources(config: RunnableConfig = None) -> dict[str, Any]:
    """Trigger a manual Feishu resource sync for the current user."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return sync_feishu_sources(
            repo,
            source_repo=SourceRepository(repo.conn),
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            triggered_by="manual",
        )


@tool
def save_generated_topic(
    direction: str,
    topics: list[str],
    selected_topic: Annotated[
        dict[str, Any] | None, InjectedState("selected_topic")
    ] = None,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """持久化用户选定的那一个选题到 Postgres 数据底座(只存选中的)。

    依据来源(官方 InjectedState,单一事实源):选题依据(evidence,含 resource_id)由前端在
    用户点选选题卡时经 `submit` 直传 graph state `selected_topic`(`{topic, evidence}`),
    **完全不经对话文本/LLM 转写**——即「卡片上展示的依据 = 落库的依据」,杜绝重填时静默丢
    resource_id。你(模型)**不要也无法在参数里传 evidence**;只需给 `direction`,`topics`
    会以用户点选的那张卡为准。

    Args:
        direction: 选题方向(用户给的方向)。
        topics: 选定的选题(回退用;若 state 带了点选的卡,则以卡上文案为准)。
    """
    final_topics = topics
    evidence: list[dict[str, Any]] | None = None
    if isinstance(selected_topic, dict):
        picked = selected_topic.get("topic")
        if isinstance(picked, str) and picked.strip():
            final_topics = [picked.strip()]
        ev = selected_topic.get("evidence")
        if isinstance(ev, list):
            evidence = ev
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_generated_topic_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            direction=direction,
            topics=final_topics,
            evidence=evidence,
        )


@tool
def save_generated_copy(
    title: str,
    body: str,
    tags: list[str],
    versions: list[dict[str, Any]] | None = None,
    resource_id: str | None = None,
    expected_resource_version: int | None = None,
    expected_state_version: int | None = None,
    source_topic: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    reference_resource_id: str | None = None,
    reference_resource_version: int | None = None,
    knowledge_grounding: Annotated[
        dict[str, Any] | None, InjectedState("knowledge_grounding")
    ] = None,
    latest_user_request: Annotated[
        str | None, InjectedState("latest_user_request")
    ] = None,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Persist a generated Xiaohongshu copy draft into the shared Postgres data foundation.

    多版本成品必须把完整 A/B/C 传入 versions；后端会一次事务冷存为同一 resource_id 的
    不可变 resource_versions，并返回每版 resource_version。候选不会进入知识检索。
    润色/重写已有文案时必须传 resource_id，让修订继续追加在同一资源；若已有
    expected_resource_version/expected_state_version 必须一并传入做并发校验；任一缺失都会
    fail closed，必须先读取最新生命周期令牌后重试，绝不静默追写到未知的新版本。

    reference_resource_id: 仿写产出时,该篇所仿的范本素材 resource_id。传入则落一条
    imitated_from 边(成品→范本),满足「仿写成品可追溯到范本原型」(§5)。非仿写留空。
    """
    actor = actor_from_config(config)
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    origin_turn_id = (
        str(configurable.get("turn_id") or "").strip()
        if isinstance(configurable, dict)
        else ""
    ) or None
    grounding = _validated_grounding_context(
        knowledge_grounding,
        expected_turn_id=origin_turn_id,
    )
    authoritative_evidence = _grounded_evidence(grounding, evidence)
    with _repository() as repo:
        # 新版本与“用户为什么要改”必须原子提交，不能出现文案已改但反馈未进入学习闭环。
        with repo.unit_of_work():
            result = save_generated_copy_resource(
                repo,
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                title=title,
                body=body,
                tags=tags,
                versions=versions,
                resource_id=resource_id,
                expected_resource_version=expected_resource_version,
                expected_state_version=expected_state_version,
                origin_turn_id=origin_turn_id,
                source_topic=source_topic,
                evidence=authoritative_evidence,
                grounding={
                    "query": grounding["query"],
                    "retrieval_mode": grounding["retrieval_mode"],
                    "turn_id": grounding.get("turn_id"),
                    "gaps": grounding.get("gaps"),
                },
                reference_resource_id=reference_resource_id,
                reference_resource_version=reference_resource_version,
            )
            feedback_text = (
                latest_user_request.strip()
                if isinstance(latest_user_request, str) and latest_user_request.strip()
                else ""
            )
            if resource_id and feedback_text:
                feedback_result = save_user_feedback_resource(
                    repo,
                    tenant_id=default_tenant_id(),
                    actor_open_id=actor,
                    feedback=feedback_text,
                    target_resource_id=resource_id,
                    target_resource_version=expected_resource_version,
                    feedback_type="revision_request",
                    idempotency_key=(
                        f"auto-revision-feedback:{origin_turn_id}"
                        if origin_turn_id
                        else None
                    ),
                )
                result["feedback_resource"] = feedback_result["resource"]
            return result


def _validated_grounding_context(
    value: dict[str, Any] | None, *, expected_turn_id: str | None
) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("status") != "ready":
        raise RuntimeError(
            "automatic retrieve_knowledge grounding is required before saving generated copy"
        )
    mode = value.get("retrieval_mode")
    evidence = value.get("evidence")
    query = value.get("query")
    if mode not in {
        "hybrid",
        "semantic_only",
        "keyword_only",
        "insufficient_relevance",
    } or not isinstance(evidence, list) or not isinstance(query, str) or not query.strip():
        raise RuntimeError("automatic knowledge grounding is invalid")
    if mode == "insufficient_relevance" and evidence:
        raise RuntimeError("insufficient_relevance grounding must not contain evidence")
    if mode != "insufficient_relevance" and not evidence:
        raise RuntimeError("successful knowledge grounding must contain evidence")
    context_turn_id = value.get("turn_id")
    if expected_turn_id and context_turn_id != expected_turn_id:
        raise RuntimeError("automatic knowledge grounding belongs to another turn")
    return value


def _grounded_evidence(
    grounding: dict[str, Any], requested: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """只允许自动检索命中的 exact identity 进入文案依据，拒绝 LLM 伪造。"""

    authoritative = [item for item in grounding["evidence"] if isinstance(item, dict)]
    by_identity = {
        (item.get("resource_id"), item.get("resource_version")): item
        for item in authoritative
    }
    for item in requested or []:
        if not isinstance(item, dict):
            raise ValueError("evidence items must be objects")
        identity = (item.get("resource_id"), item.get("resource_version"))
        if identity not in by_identity:
            raise PermissionError(
                "copy evidence must come from this turn's automatic knowledge retrieval"
            )
    return authoritative


@tool
def save_user_feedback(
    feedback: str,
    target_resource_id: str | None = None,
    target_resource_version: int | None = None,
    feedback_type: str = "user_feedback",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Persist user feedback or a revision request into the shared Postgres data foundation."""
    actor = actor_from_config(config)
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    stable_request_id = (
        tool_call_id.strip() if isinstance(tool_call_id, str) else ""
    ) or (
        str(configurable.get("turn_id") or "").strip()
        if isinstance(configurable, dict)
        else ""
    ) or None
    with _repository() as repo:
        return save_user_feedback_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            feedback=feedback,
            target_resource_id=target_resource_id,
            target_resource_version=target_resource_version,
            feedback_type=feedback_type,
            idempotency_key=stable_request_id,
        )


@tool
def save_writing_teardown(
    source_resource_id: str,
    source_resource_version: int,
    niche: str,
    hook: str,
    cta: str,
    structure: list[str],
    success_factors: list[str],
    style_tags: list[str],
    quality: float,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """保存一份小红书文案拆解，并精确关联到真实来源版本。

    source_resource_id 与 source_resource_version 必须来自检索/读取结果，禁止只凭资源 id
    猜测最新版。quality 仅保存为模型完整度自评，不参与知识资格或质量打分；工具会在
    同一事务内校验 ACL、创建版本化结构分析并写入 teardown_of 精确来源边。
    """
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_writing_teardown_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            source_resource_id=source_resource_id,
            source_resource_version=source_resource_version,
            niche=niche,
            hook=hook,
            cta=cta,
            structure=structure,
            success_factors=success_factors,
            style_tags=style_tags,
            quality=quality,
        )


@tool
def save_performance_metric(
    target_resource_id: str,
    metrics: dict[str, Any],
    target_resource_version: int | None = None,
    published_at: str | None = None,
    channel: str = "xiaohongshu",
    note_url: str | None = None,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Persist post-publish performance metrics for a generated or source content resource."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_performance_metric_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            target_resource_id=target_resource_id,
            target_resource_version=target_resource_version,
            metrics=metrics,
            published_at=published_at,
            channel=channel,
            note_url=note_url,
        )


@tool
def get_resource_performance(
    resource_id: str,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Read post-publish performance metrics linked to a readable resource."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return get_resource_performance_payload(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_id=resource_id,
        )


@tool
def get_operations_data(
    view: str,
    account: str | None = None,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """读取账号运营数据(只读,与运营看板 UI 同源、同鉴权)。

    view: analytics(数据看板/选题库/爆款拆解) | calendar(内容日历/排期) |
          pipeline(发布管线) | accounts(账号矩阵) | recents(我的最近创作) | trends(热点趋势)。
    account: 单账号过滤;不传=矩阵总览(analytics/calendar/pipeline/accounts 的矩阵总览需管理员)。
    数据为空即真实无数据,不编造。
    """
    actor = actor_from_config(config)
    tenant = default_tenant_id()
    admin = is_admin_open_id(actor)
    account = account.strip() if isinstance(account, str) and account.strip() else None

    # 鉴权口径 A:矩阵总览(不带 account)与 accounts 需 admin;单账号/recents/trends 任意用户。
    needs_admin = (account is None and view in ("analytics", "calendar", "pipeline")) or view == "accounts"
    if needs_admin and not admin:
        return {"ok": False, "error": "该视图为跨账号矩阵总览,需管理员权限;请指定 account 查看单账号,或联系管理员。"}

    # load_* 数据获取包一层脱敏:失败只记固定信息 + 异常类名(不记异常细节/DSN/路径),
    # 返回与 BFF 503 同口径的通用提示(不含异常细节),避免 ToolNode 把异常原文
    # (可能含 DSN)注入模型上下文再转告用户。鉴权拒绝在此之上,不受影响。
    try:
        if view == "analytics":
            return {"ok": True, "view": view, "account": account, **ops.load_analytics(tenant_id=tenant, account=account)}
        if view == "calendar":
            return {"ok": True, "view": view, "account": account, **ops.load_calendar(tenant_id=tenant, account=account)}
        if view == "pipeline":
            return {"ok": True, "view": view, "account": account, "queue": ops.load_pipeline(tenant_id=tenant, account=account)}
        if view == "accounts":
            return {"ok": True, "view": view, **ops.load_accounts(tenant_id=tenant)}
        if view == "recents":
            return {"ok": True, "view": view, "recents": ops.load_recents(tenant_id=tenant, open_id=actor)}
        if view == "trends":
            return {"ok": True, "view": view, "trends": ops.load_trends(tenant_id=tenant)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("operations_data_load_failed view=%s type=%s", view, type(exc).__name__)
        return {"ok": False, "error": "运营数据暂不可用,请稍后重试。"}
    return {"ok": False, "error": f"unknown view '{view}';合法值:analytics/calendar/pipeline/accounts/recents/trends。"}


@tool
def save_session_snapshot(
    project_name: str,
    title: str,
    content: str,
    snapshot_kind: Literal[
        "workflow_state",
        "diagnosis",
        "positioning",
        "decision",
        "learning_chapter",
        "content_system",
        "stage_report",
        "migration_audit",
    ],
    metadata: dict[str, Any] | None = None,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Persist an exact owner-scoped workflow checkpoint in Postgres.

    Saving does not claim that model-authored content is user-confirmed knowledge.  Use
    ``confirm_session_snapshot`` with the returned exact identity only after the user
    explicitly confirms the conclusion.  Restore checkpoints with
    ``get_session_snapshots`` rather than generic knowledge search.
    """
    actor = actor_from_config(config)
    safe_metadata = {
        key: value
        for key, value in dict(metadata or {}).items()
        if key not in {"confirmed", "confirmed_by"}
    }
    content_json = {
        **safe_metadata,
        "project_name": project_name,
        "snapshot_kind": snapshot_kind,
    }
    with _repository() as repo:
        resource = repo.upsert_resource(
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_type="session_snapshot",
            title=f"[{project_name}] {title}",
            summary=title,
            content_text=content,
            content_json=content_json,
            visibility="private",
            owner_open_id=actor,
            outbox_requests=default_write_requests(),
        )
    return {
        "ok": True,
        "resource_id": str(resource.id),
        "resource_version": int(resource.version),
        "snapshot_kind": snapshot_kind,
        "confirmation_status": "unconfirmed",
    }


@tool
def get_session_snapshots(
    project_name: str | None = None,
    limit: int = 10,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Restore the current actor's exact workflow checkpoints, including unconfirmed ones."""
    actor = actor_from_config(config)
    with _repository() as repo:
        rows = repo.list_owned_session_snapshots(
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            project_name=project_name,
            limit=limit,
        )
    return {
        "ok": True,
        "snapshots": [
            {
                "resource_id": row["resource_id"],
                "resource_version": int(row["resource_version"]),
                "title": row["title"],
                "summary": row["summary"],
                "content_text": row["content_text"],
                "content_json": dict(row["content_json"] or {}),
                "updated_at": (
                    row["updated_at"].isoformat() if row.get("updated_at") else None
                ),
            }
            for row in rows
        ],
    }


@tool
def confirm_session_snapshot(
    resource_id: str,
    resource_version: int,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """Promote one exact checkpoint to strategy knowledge after explicit user confirmation.

    Never call this merely because an agent generated a report.  The exact identity must
    come from ``save_session_snapshot``/``get_session_snapshots`` and the user must have
    explicitly accepted that conclusion in the current interaction.
    """
    actor = actor_from_config(config)
    try:
        uuid.UUID(str(resource_id))
    except (ValueError, TypeError, AttributeError):
        return {"ok": False, "error": "Session snapshot not found or not writable"}
    from data_foundation.knowledge.repository import KnowledgeRepository

    try:
        with _repository() as repo:
            result = KnowledgeRepository(repo.conn).confirm_exact_version(
                default_tenant_id(),
                actor,
                resource_id,
                resource_version,
                "strategy_fact",
                {},
            )
    except (PermissionError, ValueError):
        return {"ok": False, "error": "Session snapshot not found or not writable"}
    return {"ok": True, **result}


data_foundation_tools = [
    retrieve_knowledge,
    search_local_note_cards,
    get_resource,
    get_generated_copy_lifecycle,
    get_writing_profile,
    get_data_foundation_status,
    sync_feishu_resources,
    save_generated_topic,
    save_generated_copy,
    save_user_feedback,
    save_writing_teardown,
    save_performance_metric,
    get_resource_performance,
    get_operations_data,
    save_session_snapshot,
    get_session_snapshots,
    confirm_session_snapshot,
]
