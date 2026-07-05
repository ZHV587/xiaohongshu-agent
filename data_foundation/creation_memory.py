from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from data_foundation.models import RuntimeIdentityConfig
from data_foundation.outbox_requests import default_write_requests

DERIVED_EDGE = "derived_from"
FEEDBACK_EDGE = "feedback_on"
# §0 素材不孤立:入库素材与已有素材的关联边。
# semantically_related — 语义关联(内容分析:同垂类/同主题/相近痛点),weight=相关度。
# co_ingested — 同批收录的行为关联(兜底:语义邻居为空、库内暂无可连素材时,
#   保证同批入库的素材彼此挂边,不成孤岛)。
SEMANTIC_EDGE = "semantically_related"
CO_INGEST_EDGE = "co_ingested"
# 仿写自 — 成品文案 → 其范本素材的行为关联(§5 可追溯)。
IMITATED_EDGE = "imitated_from"


def _actor_can_read(repo: Any, *, tenant_id: str, actor_open_id: str, target_resource_id: str) -> bool:
    """校验 actor 是否对 target 有读权限。

    P1 安全:用户提交的 evidence[].resource_id / 反馈 target_resource_id 是不可信输入,
    生产 add_edge 只校 tenant、不校 actor 权限 —— 否则用户可建边到他人私有资源(graph_ingest
    materialize 后经图遍历暴露其存在)。故在边写入前,于编排层对每个用户提供的 target 做读权限闸门。
    repo 无 check_permission(测试假仓)时放行,真实 ResourceRepository 强制校验。
    """
    check = getattr(repo, "check_permission", None)
    if not callable(check):
        return True
    actor = RuntimeIdentityConfig(tenant_id=tenant_id, open_id=actor_open_id)
    try:
        check(target_resource_id, actor, permission="read", conn=getattr(repo, "conn", None))
        return True
    except PermissionError:
        return False


def save_generated_topic_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    direction: str,
    topics: list[str],
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    direction = direction.strip()
    if not direction:
        raise ValueError("direction is required")
    topics = _clean_strings(topics, field="topics")
    cleaned_evidence = _clean_evidence(evidence)
    with _unit_of_work(repo):
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_type="generated_topic",
            title=f"{direction} 选题",
            summary="; ".join(topics[:3]),
            content_text="\n".join(f"- {topic}" for topic in topics),
            content_json={"direction": direction, "topics": topics, "evidence": cleaned_evidence},
            visibility="team",
            owner_open_id=actor_open_id,
            outbox_requests=default_write_requests(),
        )
        _link_evidence(repo, tenant_id=tenant_id, actor_open_id=actor_open_id, generated_id=resource.id, evidence=cleaned_evidence)
        return _payload(resource, cleaned_evidence)


def save_generated_copy_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    title: str,
    body: str,
    tags: list[str],
    source_topic: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    reference_resource_id: str | None = None,
) -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ValueError("title is required")
    body = body.strip()
    if not body:
        raise ValueError("body is required")
    cleaned_tags = [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()]
    cleaned_evidence = _clean_evidence(evidence)
    source_topic = source_topic.strip() if isinstance(source_topic, str) and source_topic.strip() else None
    parts = [title, "", body]
    if cleaned_tags:
        parts.extend(["", " ".join(cleaned_tags)])
    with _unit_of_work(repo):
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_type="generated_copy",
            title=title,
            summary=source_topic,
            content_text="\n".join(parts),
            content_json={
                "title": title,
                "body": body,
                "tags": cleaned_tags,
                "source_topic": source_topic,
                "evidence": cleaned_evidence,
            },
            visibility="team",
            owner_open_id=actor_open_id,
            outbox_requests=default_write_requests(),
        )
        _link_evidence(repo, tenant_id=tenant_id, actor_open_id=actor_open_id, generated_id=resource.id, evidence=cleaned_evidence)
        # §5 仿写可追溯:若本篇是仿写产出,对范本素材建 imitated_from 边(成品→范本)。
        # 与 _link_evidence 同一 unit_of_work 内,失败随事务回滚(与证据边一致)。
        if reference_resource_id:
            link_imitation_source(
                repo, tenant_id=tenant_id, actor_open_id=actor_open_id,
                copy_resource_id=resource.id, reference_resource_id=reference_resource_id,
            )
        return _payload(resource, cleaned_evidence)


def save_user_feedback_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    feedback: str,
    target_resource_id: str | None = None,
    feedback_type: str = "user_feedback",
) -> dict[str, Any]:
    feedback = feedback.strip()
    if not feedback:
        raise ValueError("feedback is required")
    if feedback_type not in {"user_feedback", "revision_request"}:
        raise ValueError("feedback_type must be user_feedback or revision_request")
    target_resource_id = (
        target_resource_id.strip()
        if isinstance(target_resource_id, str) and target_resource_id.strip()
        else None
    )
    if feedback_type == "revision_request" and not target_resource_id:
        raise ValueError("target_resource_id is required for revision_request")
    with _unit_of_work(repo):
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_type=feedback_type,
            title="用户反馈" if feedback_type == "user_feedback" else "修改意见",
            summary=feedback[:120],
            content_text=feedback,
            content_json={"feedback": feedback, "target_resource_id": target_resource_id},
            visibility="team",
            owner_open_id=actor_open_id,
            outbox_requests=default_write_requests(),
        )
        if target_resource_id:
            # 仅当 actor 对 target 有读权限才建反馈边(防越权连到他人私有资源)。
            # revision_request 已强制要求 target,但其权限同样需校验。
            if _actor_can_read(
                repo, tenant_id=tenant_id, actor_open_id=actor_open_id,
                target_resource_id=target_resource_id,
            ):
                repo.add_edge(
                    tenant_id=tenant_id,
                    source_resource_id=resource.id,
                    target_resource_id=target_resource_id,
                    edge_type=FEEDBACK_EDGE,
                    weight=1.0,
                )
    return _payload(resource, [])


def _clean_strings(values: list[str], *, field: str) -> list[str]:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not cleaned:
        raise ValueError(f"{field} must contain at least one non-empty string")
    return cleaned


def _clean_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        resource_id = item.get("resource_id")
        if not isinstance(resource_id, str) or not resource_id.strip():
            continue
        resource_id = resource_id.strip()
        if resource_id in seen:
            continue
        seen.add(resource_id)
        cleaned_item = {
            "resource_id": resource_id,
            "title": _clean_optional_string(item.get("title")),
            "summary": _clean_optional_string(item.get("summary")),
            "source_updated_at": _clean_optional_string(item.get("source_updated_at")),
            "indexed_at": _clean_optional_string(item.get("indexed_at")),
        }
        cleaned.append(cleaned_item)
    return cleaned


def _link_evidence(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    generated_id: str,
    evidence: list[dict[str, str]],
) -> None:
    for item in evidence:
        target = item["resource_id"]
        # evidence resource_id 是用户/LLM 提供的不可信输入:只对 actor 可读的 target 建 derived_from
        # 边,跳过无权读的(防越权连到他人私有资源),与 _clean_evidence「丢坏的、继续」一致。
        if not _actor_can_read(
            repo, tenant_id=tenant_id, actor_open_id=actor_open_id, target_resource_id=target,
        ):
            continue
        repo.add_edge(
            tenant_id=tenant_id,
            source_resource_id=generated_id,
            target_resource_id=target,
            edge_type=DERIVED_EDGE,
            weight=1.0,
        )


def associate_ingested_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_id: str,
    neighbors: list[dict[str, Any]],
    co_ingested_ids: list[str] | None = None,
    max_edges: int = 3,
) -> dict[str, Any]:
    """§0 素材不孤立:给新入库素材挂至少一条关联边,永不成孤岛。

    这是「凡有素材入库,都要与已有素材建立至少一条关联」原则的落地(CLAUDE.md 最高原则)。
    关联由底层图结构(resource_edges → FalkorDB)承载,与 derived_from/feedback_on 同机制。

    优先级:
    1. **语义/主题关联**(强/次强):`neighbors` 是调用方经语义或全文检索得到的候选
       (每条含 resource_id、score),对每个 actor 可读、非自身的邻居建 `semantically_related`
       边,weight 取归一化 score。取前 `max_edges` 条。
    2. **同批收录关联**(行为兜底):语义邻居一条都没建成(库内暂无可连素材、或候选全不可读)
       时,退化为把同批 `co_ingested_ids` 里的其它素材挂 `co_ingested` 边,保证不孤岛。
    3. 若既无邻居又无同批伙伴(全库第一条素材),返回 isolated=True,由调用方据实记录
       ——这是唯一允许无边的情形(此时根本没有「已有素材」可连)。

    `neighbors` 的 resource_id 是检索命中(库内真实),但仍按不可信输入处理:逐个过 actor
    读权限闸门(与 _link_evidence 一致),不可读的跳过。resource 自身与已连过的目标去重。

    Returns: {"semantic": n_semantic, "co_ingested": n_co, "isolated": bool}
    """
    linked: set[str] = set()
    n_semantic = 0
    for item in neighbors:
        if n_semantic >= max_edges:
            break
        if not isinstance(item, dict):
            continue
        target = item.get("resource_id")
        if not isinstance(target, str) or not target.strip():
            continue
        target = target.strip()
        if target == resource_id or target in linked:
            continue
        if not _actor_can_read(
            repo, tenant_id=tenant_id, actor_open_id=actor_open_id, target_resource_id=target,
        ):
            continue
        try:
            weight = float(item.get("score") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        # weight 归一化到 (0,1];检索 score 已在此区间,异常值兜底为弱关联 0.1。
        if not (0.0 < weight <= 1.0):
            weight = 0.1
        repo.add_edge(
            tenant_id=tenant_id,
            source_resource_id=resource_id,
            target_resource_id=target,
            edge_type=SEMANTIC_EDGE,
            weight=weight,
        )
        linked.add(target)
        n_semantic += 1

    n_co = 0
    if n_semantic == 0:
        # 语义/主题关联一条都没建成 → 行为兜底:同批收录的其它素材互挂 co_ingested。
        for other in co_ingested_ids or []:
            if not isinstance(other, str) or not other.strip():
                continue
            other = other.strip()
            if other == resource_id or other in linked:
                continue
            # 同批伙伴是本次同一入库动作产生的资源,同 actor 同 tenant,天然可读;
            # 仍走 add_edge 的 tenant 端点校验(FeedbackRepository 内)兜底。
            repo.add_edge(
                tenant_id=tenant_id,
                source_resource_id=resource_id,
                target_resource_id=other,
                edge_type=CO_INGEST_EDGE,
                weight=1.0,
            )
            linked.add(other)
            n_co += 1

    return {"semantic": n_semantic, "co_ingested": n_co, "isolated": not linked}


def link_imitation_source(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    copy_resource_id: str,
    reference_resource_id: str,
) -> bool:
    """§5 仿写可追溯:成品文案 → 范本素材建 imitated_from 边。

    reference_resource_id 由前端直传(用户在素材卡上点「仿写」的那一篇),按不可信输入处理:
    过 actor 读权限闸门,不可读则不建边并返回 False(与 _link_evidence 一致)。
    """
    reference_resource_id = (
        reference_resource_id.strip()
        if isinstance(reference_resource_id, str) and reference_resource_id.strip()
        else ""
    )
    if not reference_resource_id or reference_resource_id == copy_resource_id:
        return False
    if not _actor_can_read(
        repo, tenant_id=tenant_id, actor_open_id=actor_open_id,
        target_resource_id=reference_resource_id,
    ):
        return False
    repo.add_edge(
        tenant_id=tenant_id,
        source_resource_id=copy_resource_id,
        target_resource_id=reference_resource_id,
        edge_type=IMITATED_EDGE,
        weight=1.0,
    )
    return True


def _payload(resource: Any, evidence: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "ok": True,
        "resource": {
            "resource_id": resource.id,
            "type": resource.type,
            "title": resource.title,
            "version": resource.version,
        },
        "evidence_count": len(evidence),
    }


def _clean_optional_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _unit_of_work(repo: Any):
    unit_of_work = getattr(repo, "unit_of_work", None)
    return unit_of_work() if callable(unit_of_work) else nullcontext()
