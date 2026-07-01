from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

import httpx
import psycopg
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from data_foundation.creation_memory import (
    save_generated_copy_resource,
    save_generated_topic_resource,
    save_user_feedback_resource,
)
from data_foundation.config import embedding_snapshot_for_version
from data_foundation.graph import expand_graph as expand_graph_query
from data_foundation import operations as ops
from data_foundation.outbox_requests import default_write_requests
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.studio_shared import is_admin_open_id, repository as _repository
from data_foundation.performance_feedback import (
    get_resource_performance_payload,
    save_performance_metric_resource,
)
from data_foundation.processors.embedding import EmbeddingProviderConfig, embedding_config_from_snapshot
from data_foundation.search import semantic_search
from data_foundation.source_repository import SourceRepository
from data_foundation.sync_service import sync_feishu_sources


logger = logging.getLogger(__name__)


class EmbeddingSearchUnavailable(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _embedding_query_config_for_index(active_index: Any) -> EmbeddingProviderConfig:
    config_version = str(getattr(active_index, "config_version", "") or "").strip()
    if not config_version:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_PROFILE_UNAVAILABLE")
    snapshot = embedding_snapshot_for_version(config_version)
    if snapshot is None:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_PROFILE_UNAVAILABLE")
    provider_config = embedding_config_from_snapshot(snapshot)
    if provider_config is None:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_CONFIG_MISSING")
    if provider_config.state != "enabled":
        raise EmbeddingSearchUnavailable(provider_config.reason_code or "EMBEDDING_QUERY_CONFIG_INVALID")
    if (
        provider_config.model != active_index.embedding_model
        or provider_config.dimensions != active_index.dimensions
    ):
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_PROFILE_MISMATCH")
    return provider_config


def _embed_query(query: str, *, config: EmbeddingProviderConfig, query_instruction: str | None) -> list[float]:
    text = query if not query_instruction else query_instruction.format(query=query)
    response = httpx.post(
        config.base_url.rstrip("/") + "/embeddings",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json={"model": config.model, "input": [text], "dimensions": config.dimensions},
        timeout=config.timeout_seconds,
    )
    if response.status_code in {401, 403}:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_UNAUTHORIZED")
    response.raise_for_status()
    data = response.json().get("data", [])
    if len(data) != 1:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_BAD_RESPONSE")
    return [float(value) for value in data[0]["embedding"]]


def _search_payload(results: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "resource_id": item.resource_id,
            "title": item.title,
            "summary": item.summary,
            "score": item.score,
            "metadata": item.metadata,
        }
        for item in results
    ]


def _rows_to_payload(rows: list[Any]) -> list[dict[str, Any]]:
    payload = []
    for row in rows:
        meta = {"type": row["type"], "visibility": row["visibility"]}
        if row.get("source_updated_at"):
            meta["source_updated_at"] = row["source_updated_at"].isoformat()
        if row.get("updated_at"):
            meta["indexed_at"] = row["updated_at"].isoformat()
        payload.append({
            "resource_id": str(row["id"]),
            "title": row["title"],
            "summary": row["summary"],
            "score": float(row.get("score") or 0),
            "metadata": meta,
        })
    return payload


@tool
def search_local_note_cards(keyword: str, limit: int = 12, config: RunnableConfig | None = None) -> dict[str, Any]:
    """检索本地已收录笔记,返回细致卡片字段(封面/互动/标签)用于发现面板展示。

    与 search_resources(证据链)分离:本工具 hydrate content_json 输出统一卡片形状,
    不影响 rank_evidence / EvidencePackage。
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
        return {"ok": False, "error": f"MEILI_QUERY_FAILED: {exc}", "results": []}
    ids = [rid for rid, _ in hits]
    score_by_id = {rid: score for rid, score in hits}
    with _repository() as repo:
        rows = repo.readable_rows_by_ids(
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_ids=ids,
        )
    cards: list[dict[str, Any]] = []
    for row in rows:
        content_json = dict(row["content_json"]) if row.get("content_json") is not None else {}
        card = hydrate_note_card(
            str(row["id"]),
            row["type"],
            content_json,
            score=score_by_id.get(str(row["id"]), 0.0),
        )
        if card is not None:
            cards.append(card)
    cards = dedupe_by_note_url(cards)
    return {"ok": True, "results": cards[:want]}


@tool
def search_resources(query: str, limit: int = 10, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Search readable resources by full-text (Meilisearch) and return summaries only."""
    actor = actor_from_config(config)
    from data_foundation.engine_config import meili_config_from_env
    from data_foundation.meili_client import MeiliResourceIndex
    from data_foundation.search_ranker import rank_evidence

    cfg = meili_config_from_env()
    if cfg.state != "enabled":
        return {"ok": False, "error": "MEILI_UNAVAILABLE"}
    want = min(max(int(limit), 1), 20)
    # Meili 只按 tenant 过滤(无行级 owner/visibility ACL),权限裁决在 PG 后置。
    # 若只取 want 个 id 再过权限,命中里他人私有资源会挤掉可读结果 → 静默欠召回,
    # 极端返回空让 agent 误判"无数据"。故 over-fetch(want*5,上限 200),PG 过权限后
    # 按相关性序(readable_rows_by_ids 保序)截断到 want。
    over_fetch = min(want * 5, 200)
    try:
        index = MeiliResourceIndex.from_config(cfg)
        hits = index.search(query.strip(), tenant_id=default_tenant_id(), limit=over_fetch)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"MEILI_QUERY_FAILED: {exc}"}
    ids = [rid for rid, _ in hits]
    score_by_id = {rid: score for rid, score in hits}
    with _repository() as repo:
        rows = repo.readable_rows_by_ids(
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_ids=ids,
        )
        valid_ids = [str(r["id"]) for r in rows]
        perf_data = repo.bulk_performance_metrics(
            tenant_id=default_tenant_id(),
            resource_ids=valid_ids,
        )
    raw_results = _rows_to_payload(rows)
    # 注入 Meili ranking 分数:_rows_to_payload 取的 PG 行不含 BM25 相关度,
    # 用 Meili _rankingScore 覆盖,作为 score_kind="bm25" 的归一化依据。
    for item in raw_results:
        item["score"] = score_by_id.get(item["resource_id"], 0.0)
    ranked_results = rank_evidence(
        tenant_id=default_tenant_id(),
        results=raw_results,
        performance_data=perf_data,
        limit=want,
        score_kind="bm25",
    )
    return {"ok": True, "results": ranked_results}


@tool
def semantic_search_resources(query: str, top_k: int = 10, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Search readable resources by configured embedding provider and pgvector."""
    actor = actor_from_config(config)
    from data_foundation.config import current_relevance_floor, resolve_query_instruction
    from data_foundation.search_ranker import rank_evidence

    # top_k clamp:对齐 search_resources 的 [1,20]。负值会让 rank_evidence 的 [:top_k]
    # 从尾部丢结果、0 直接返回空,均非预期;LLM 偶发传 0/负也不该出错。
    top_k = min(max(int(top_k), 1), 20)

    def _fulltext_fallback(reason: str) -> dict[str, Any]:
        # 语义不可用时降级到全文(Meilisearch),与设计一致(全文引擎=Meili,非 PG)
        fallback = search_resources.func(query, limit=top_k, config=config)
        if not fallback.get("ok"):
            return {"ok": False, "mode": "keyword_fallback", "fallback_reason": reason,
                    "error": fallback.get("error"), "results": []}
        return {"ok": True, "mode": "keyword_fallback", "fallback_reason": reason,
                "results": fallback.get("results", [])}

    if not query or not query.strip():
        # 空查询不送 provider(避免空文本 embedding 触发 provider 报错),直接走全文。
        return _fulltext_fallback("EMPTY_QUERY")

    with _repository() as repo:
        try:
            active_index = repo.active_embedding_index(default_tenant_id())
            if active_index is None:
                return _fulltext_fallback("NO_ACTIVE_EMBEDDING_INDEX")
            query_config = _embedding_query_config_for_index(active_index)
            # 检索期策略从当前配置解析(不随 active index config_version 历史回放):
            # 模型名取 active index(判定 Qwen3),显式覆盖取当前配置。
            query_instruction = resolve_query_instruction(query_config.model)
            embedding = _embed_query(query, config=query_config, query_instruction=query_instruction)
            results = semantic_search(
                repo,
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                embedding=embedding,
                embedding_model=active_index.embedding_model,
                top_k=top_k * 5,
            )
        except EmbeddingSearchUnavailable as exc:
            return _fulltext_fallback(exc.reason_code)
        except httpx.HTTPError as exc:
            # provider 5xx/429/超时/连接拒绝等运行时网络异常:降级到全文,不崩工具。
            return _fulltext_fallback(f"EMBEDDING_QUERY_HTTP_ERROR: {type(exc).__name__}")
        except ValueError as exc:
            # 向量校验失败(provider 忽略 dimensions 返回非预期维度、含 NaN 等):降级。
            return _fulltext_fallback(f"EMBEDDING_QUERY_INVALID_VECTOR: {exc}")
        except (psycopg.Error, KeyError) as exc:
            # pgvector/PG 查询级故障(向量维度不符、扩展缺失、事务 abort、瞬时错误)或
            # provider 响应缺 embedding 键:按设计契约降级到全文,不让工具硬崩。
            return _fulltext_fallback(f"EMBEDDING_QUERY_DB_ERROR: {type(exc).__name__}")

        # 候选集为空:active index 存在但目标资源尚未被 embed(典型:刚 save_generated_*
        # 后台 reconcile 还没补 embedding,而 meili_index 已在同一 cycle 投递可命中)。
        # 这是"引擎暂时没话说",不是"库内无相关内容" → 降级到全文,别误报数据不足。
        if not results:
            return _fulltext_fallback("NO_SEMANTIC_CANDIDATES")

        # --- 绝对相关度闸门:基于原始绝对余弦,在 rank_evidence 加权之前 ---
        # 阈值取当前配置(不随历史回放)。候选**非空但全部低于阈值**=库内确有内容但都不够相关
        # → 明确"数据不足",不返回弱相关结果、不降级到 BM25(避免误命中重新混入)。
        floor = current_relevance_floor()
        top_score = max(res.score for res in results)
        if top_score < floor:
            return {
                "ok": True,
                "mode": "insufficient_relevance",
                "results": [],
                "top_score": round(top_score, 4),
                "threshold": floor,
            }

        valid_ids = [res.resource_id for res in results]
        try:
            perf_data = repo.bulk_performance_metrics(
                tenant_id=default_tenant_id(),
                resource_ids=valid_ids,
            )
        except psycopg.Error:
            # 效果指标只是排序加权增强项,查询失败不该让已拿到的语义结果崩;退化为无表现分。
            perf_data = {rid: [] for rid in valid_ids}
    raw_results = _search_payload(results)
    ranked_results = rank_evidence(
        tenant_id=default_tenant_id(),
        results=raw_results,
        performance_data=perf_data,
        limit=top_k,
        score_kind="cosine",
    )
    return {"ok": True, "mode": "semantic", "results": ranked_results}


@tool
def get_resource(resource_id: str, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Read one resource body after tenant and permission filtering."""
    actor = actor_from_config(config)
    # resources.id 是 uuid 列,where r.id=%s 对非 UUID 串会抛 22P02 invalid uuid 并冒泡。
    # LLM 常传幻觉 id/标题(如 "generated-1"),按契约应返回 not found 而非把 SQL 错误回给模型。
    try:
        uuid.UUID(str(resource_id))
    except (ValueError, TypeError, AttributeError):
        return {"ok": False, "error": "Resource not found or not permitted"}
    with _repository() as repo:
        resource = repo.get_resource(default_tenant_id(), actor, resource_id)
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
def graph_expand(
    resource_ids: list[str],
    hops: int = 1,
    edge_types: list[str] | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Expand readable graph context from resource ids."""
    actor = actor_from_config(config)
    try:
        with _repository() as repo:
            graph = expand_graph_query(
                repo,
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                resource_ids=resource_ids,
                hops=hops,
                edge_types=edge_types,
            )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"GRAPH_UNAVAILABLE: {exc}"}
    return {
        "ok": True,
        "nodes": [node.__dict__ for node in graph.nodes],
        "edges": [edge.__dict__ for edge in graph.edges],
    }


@tool
def get_data_foundation_status(config: RunnableConfig | None = None) -> dict[str, Any]:
    """Return Postgres data foundation resource, sync, and outbox status."""
    actor_from_config(config)
    with _repository() as repo:
        status = repo.data_foundation_status(default_tenant_id())
    return {"ok": True, "status": status}


@tool
def sync_feishu_resources(config: RunnableConfig | None = None) -> dict[str, Any]:
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
    config: RunnableConfig | None = None,
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
    source_topic: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist a generated Xiaohongshu copy draft into the shared Postgres data foundation."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_generated_copy_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            title=title,
            body=body,
            tags=tags,
            source_topic=source_topic,
            evidence=evidence,
        )


@tool
def save_user_feedback(
    feedback: str,
    target_resource_id: str | None = None,
    feedback_type: str = "user_feedback",
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist user feedback or a revision request into the shared Postgres data foundation."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_user_feedback_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            feedback=feedback,
            target_resource_id=target_resource_id,
            feedback_type=feedback_type,
        )


@tool
def save_performance_metric(
    target_resource_id: str,
    metrics: dict[str, Any],
    published_at: str | None = None,
    channel: str = "xiaohongshu",
    note_url: str | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist post-publish performance metrics for a generated or source content resource."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_performance_metric_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            target_resource_id=target_resource_id,
            metrics=metrics,
            published_at=published_at,
            channel=channel,
            note_url=note_url,
        )


@tool
def get_resource_performance(
    resource_id: str,
    config: RunnableConfig | None = None,
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
    config: RunnableConfig | None = None,
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
    metadata: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist session state, account positioning, diagnosis, or report snapshots into the Postgres database.
    Use this for session diagnostics database persistence instead of only saving locally.
    """
    actor = actor_from_config(config)
    with _repository() as repo:
        resource = repo.upsert_resource(
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_type="session_snapshot",
            title=f"[{project_name}] {title}",
            summary=title,
            content_text=content,
            content_json=metadata or {},
            visibility="team",
            owner_open_id=actor,
            outbox_requests=default_write_requests(),
        )
    return {"ok": True, "resource_id": str(resource.id)}


data_foundation_tools = [
    search_resources,
    search_local_note_cards,
    semantic_search_resources,
    graph_expand,
    get_resource,
    get_data_foundation_status,
    sync_feishu_resources,
    save_generated_topic,
    save_generated_copy,
    save_user_feedback,
    save_performance_metric,
    get_resource_performance,
    get_operations_data,
    save_session_snapshot,
]

