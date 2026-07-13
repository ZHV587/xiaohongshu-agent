from __future__ import annotations

from contextlib import nullcontext
import hashlib
import json
from typing import Any
import uuid

from data_foundation.outbox_requests import candidate_graph_requests, default_write_requests

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
FEEDBACK_NAMESPACE = uuid.UUID("a7cd925a-6978-43c2-9ba5-b5648c30d2ad")


def _actor_can_read(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    target_resource_id: str,
    target_resource_version: int,
) -> bool:
    """校验 actor 是否对 target 有读权限。

    P1 安全:用户提交的 evidence[].resource_id / 反馈 target_resource_id 是不可信输入,
    生产 add_edge 只校 tenant、不校 actor 权限 —— 否则用户可建边到他人私有资源(graph_ingest
    materialize 后经图遍历暴露其存在)。故在边写入前,于编排层对每个用户提供的 target 做读权限闸门。
    repo 无 check_permission(测试假仓)时放行,真实 ResourceRepository 强制校验。
    """
    return repo.get_resource_version(
        tenant_id,
        actor_open_id,
        target_resource_id,
        target_resource_version,
    ) is not None


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
        _link_evidence(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            generated_id=resource.id,
            generated_version=int(resource.version),
            evidence=cleaned_evidence,
        )
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
    reference_resource_version: int | None = None,
    versions: list[dict[str, Any]] | None = None,
    resource_id: str | None = None,
    expected_resource_version: int | None = None,
    expected_state_version: int | None = None,
    origin_turn_id: str | None = None,
) -> dict[str, Any]:
    implicit_single_revision = versions is None
    candidates = _clean_copy_candidates(title=title, body=body, tags=tags, versions=versions)
    canonical = candidates[0]
    cleaned_evidence = _clean_evidence(evidence)
    source_topic = source_topic.strip() if isinstance(source_topic, str) and source_topic.strip() else None
    with _unit_of_work(repo):
        is_real_repo = callable(getattr(getattr(repo, "conn", None), "transaction", None))
        lifecycle = None
        if is_real_repo:
            from data_foundation.repositories.generated_copy import GeneratedCopyRepository

            lifecycle = GeneratedCopyRepository(repo)
        existing_resource_id = resource_id.strip() if isinstance(resource_id, str) else ""
        if existing_resource_id:
            if lifecycle is None:
                raise RuntimeError("resource_id revisions require a connection-bound repository")
            if (
                not isinstance(expected_resource_version, int)
                or isinstance(expected_resource_version, bool)
                or expected_resource_version <= 0
                or not isinstance(expected_state_version, int)
                or isinstance(expected_state_version, bool)
                or expected_state_version <= 0
            ):
                raise ValueError(
                    "existing resource revisions require expected_resource_version "
                    "and expected_state_version"
                )
            current_resource_version = expected_resource_version
            current_state_version = expected_state_version
            candidate_versions: list[dict[str, Any]] = []
            for candidate in candidates:
                state = lifecycle.save_revision(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    resource_id=existing_resource_id,
                    expected_resource_version=current_resource_version,
                    expected_state_version=current_state_version,
                    title=candidate["title"],
                    body=candidate["body"],
                    tags=candidate["tags"],
                    label=None if implicit_single_revision else candidate["label"],
                    cover=candidate["cover"],
                    note=candidate["note"],
                )
                current_resource_version = state.latest_resource_version
                current_state_version = state.state_version
                candidate_versions.append(
                    {
                        "label": state.selected_label,
                        "resource_version": current_resource_version,
                        "title": candidate["title"],
                    }
                )
            # save_revision 逐条追加时 selected 会暂指最后一版；候选集 canonical 永远是首版 A，
            # 在同一外层事务内显式选回首版，保证返回映射、生命周期指针和前端默认选择一致。
            if len(candidate_versions) > 1:
                selected = lifecycle.select_version(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    resource_id=existing_resource_id,
                    resource_version=candidate_versions[0]["resource_version"],
                    expected_state_version=current_state_version,
                    label=candidate_versions[0]["label"],
                )
                current_state_version = selected.state_version
            _link_copy_versions(
                repo,
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                copy_resource_id=existing_resource_id,
                candidate_versions=candidate_versions,
                evidence=cleaned_evidence,
                reference_resource_id=reference_resource_id,
                reference_resource_version=reference_resource_version,
                source_topic=source_topic,
            )
            return {
                "ok": True,
                "resource": {
                    "resource_id": existing_resource_id,
                    "type": "generated_copy",
                    "title": candidates[0]["title"],
                    "resource_version": candidate_versions[0]["resource_version"],
                    "latest_resource_version": current_resource_version,
                    "state_version": current_state_version,
                    "versions": candidate_versions,
                },
                "evidence_count": len(cleaned_evidence),
            }
        if lifecycle is not None and origin_turn_id:
            lifecycle.lock_origin(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                origin_turn_id=origin_turn_id,
            )
            replay = lifecycle.find_by_origin(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                origin_turn_id=origin_turn_id,
            )
            if replay is not None:
                return replay
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_type="generated_copy",
            title=canonical["title"],
            summary=source_topic,
            content_text=_copy_text(canonical),
            content_json=_copy_json(canonical, source_topic=source_topic, evidence=cleaned_evidence),
            visibility="team",
            owner_open_id=actor_open_id,
            # 普通文案候选不进入可检索知识；只同步图，明确采纳/定稿后再索引精确版本。
            outbox_requests=candidate_graph_requests(),
        )
        candidate_versions = [
            {
                "label": canonical["label"],
                "resource_version": int(resource.version),
                "title": canonical["title"],
            }
        ]
        first_version = int(resource.version)
        for candidate in candidates[1:]:
            resource = repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=resource.id,
                resource_type="generated_copy",
                title=candidate["title"],
                summary=source_topic,
                content_text=_copy_text(candidate),
                content_json=_copy_json(
                    candidate, source_topic=source_topic, evidence=cleaned_evidence
                ),
                visibility="team",
                owner_open_id=actor_open_id,
                # 同一 stable resource 的其余候选只追加不可变版本，不单独进索引/图节点。
                outbox_requests=[],
            )
            candidate_versions.append(
                {
                    "label": candidate["label"],
                    "resource_version": int(resource.version),
                    "title": candidate["title"],
                }
            )
        _link_copy_versions(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            copy_resource_id=resource.id,
            candidate_versions=candidate_versions,
            evidence=cleaned_evidence,
            reference_resource_id=reference_resource_id,
            reference_resource_version=reference_resource_version,
            source_topic=source_topic,
        )
        # 生产仓储绑定连接时，同一事务初始化生命周期；测试假仓不伪造数据库状态。
        if lifecycle is not None:
            state = lifecycle.initialize_candidate(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=resource.id,
                resource_version=first_version,
                label=canonical["label"],
                candidates=candidate_versions,
                origin_turn_id=origin_turn_id,
            )
            state_version = state.state_version
        else:
            state_version = None
        payload = _payload(resource, cleaned_evidence)
        payload["resource"]["title"] = canonical["title"]
        payload["resource"].pop("version", None)
        payload["resource"]["resource_version"] = first_version
        payload["resource"]["latest_resource_version"] = int(resource.version)
        payload["resource"]["state_version"] = state_version
        payload["resource"]["versions"] = candidate_versions
        return payload


def _clean_copy_candidates(
    *,
    title: Any,
    body: Any,
    tags: Any,
    versions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    raw = versions if versions is not None else [{"title": title, "body": body, "tags": tags, "label": "A"}]
    if not isinstance(raw, list) or not raw:
        raise ValueError("versions must contain at least one candidate")
    if len(raw) > 3:
        raise ValueError("versions must contain at most 3 candidates")
    cleaned: list[dict[str, Any]] = []
    labels: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError("each version must be an object")
        candidate_title = item.get("title")
        candidate_body = item.get("body")
        candidate_tags = item.get("tags")
        if not isinstance(candidate_title, str) or not candidate_title.strip():
            raise ValueError("each version title is required")
        if not isinstance(candidate_body, str) or not candidate_body.strip():
            raise ValueError("each version body is required")
        if not isinstance(candidate_tags, list):
            raise ValueError("each version tags must be an array")
        default_label = chr(ord("A") + index)
        label = item.get("label")
        label = label.strip()[:20] if isinstance(label, str) and label.strip() else default_label
        if label in labels:
            raise ValueError("version labels must be unique")
        labels.add(label)
        cleaned.append(
            {
                "label": label,
                "title": candidate_title.strip(),
                "body": candidate_body.strip(),
                "tags": [tag.strip() for tag in candidate_tags if isinstance(tag, str) and tag.strip()],
                "cover": item.get("cover").strip() if isinstance(item.get("cover"), str) else "",
                "note": item.get("note").strip() if isinstance(item.get("note"), str) else "",
            }
        )
    if versions is not None:
        top_title = title.strip() if isinstance(title, str) else ""
        top_body = body.strip() if isinstance(body, str) else ""
        if not isinstance(tags, list):
            raise ValueError("top-level tags must be an array")
        top_tags = [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()]
        if (
            cleaned[0]["title"] != top_title
            or cleaned[0]["body"] != top_body
            or cleaned[0]["tags"] != top_tags
        ):
            raise ValueError("top-level title/body/tags must match the first version")
    return cleaned


def _copy_json(
    candidate: dict[str, Any], *, source_topic: str | None, evidence: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "title": candidate["title"],
        "body": candidate["body"],
        "tags": candidate["tags"],
        "cover": candidate["cover"],
        "note": candidate["note"],
        "variant_label": candidate["label"],
        "source_topic": source_topic,
        "evidence": evidence,
    }


def _copy_text(candidate: dict[str, Any]) -> str:
    parts = [candidate["title"], "", candidate["body"]]
    if candidate["tags"]:
        parts.extend(["", " ".join(candidate["tags"])])
    return "\n".join(parts)


def save_user_feedback_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    feedback: str,
    target_resource_id: str | None = None,
    target_resource_version: int | None = None,
    feedback_type: str = "user_feedback",
    idempotency_key: str | None = None,
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
    if target_resource_id:
        target_resource_version = _required_version(
            target_resource_version, field="target_resource_version"
        )
    feedback_payload = {
        "feedback": feedback,
        "target_resource_id": target_resource_id,
        "target_resource_version": target_resource_version,
        "feedback_type": feedback_type,
    }
    stable_request = (
        idempotency_key.strip()
        if isinstance(idempotency_key, str) and idempotency_key.strip()
        else hashlib.sha256(
            json.dumps(
                feedback_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
    )
    stable_identity = f"{tenant_id}:{actor_open_id}:{stable_request}"
    feedback_resource_id = str(uuid.uuid5(FEEDBACK_NAMESPACE, stable_identity))
    with _unit_of_work(repo):
        existing = None
        get_resource = getattr(repo, "get_resource", None)
        if callable(get_resource):
            existing = get_resource(tenant_id, actor_open_id, feedback_resource_id)
        expected_content = {**feedback_payload, "idempotency_key": stable_request}
        if existing is not None and (
            str(getattr(existing, "content_text", "") or "") != feedback
            or dict(getattr(existing, "content_json", {}) or {}) != expected_content
        ):
            raise ValueError("idempotency_key was already used with a different feedback payload")
        idempotent_replay = existing is not None
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=feedback_resource_id,
            resource_type=feedback_type,
            title="用户反馈" if feedback_type == "user_feedback" else "修改意见",
            summary=feedback[:120],
            content_text=feedback,
            content_json=expected_content,
            visibility="private",
            owner_open_id=actor_open_id,
            mapping={
                "system": "internal",
                "external_type": "user_feedback",
                "external_id": stable_identity,
                "sync_status": "synced",
            },
            outbox_requests=default_write_requests(),
        )
        if target_resource_id:
            # 仅当 actor 对 target 有读权限才建反馈边(防越权连到他人私有资源)。
            # revision_request 已强制要求 target,但其权限同样需校验。
            if _actor_can_read(
                repo, tenant_id=tenant_id, actor_open_id=actor_open_id,
                target_resource_id=target_resource_id,
                target_resource_version=int(target_resource_version),
            ):
                repo.add_edge(
                    tenant_id=tenant_id,
                    source_resource_id=resource.id,
                    source_resource_version=int(resource.version),
                    target_resource_id=target_resource_id,
                    target_resource_version=int(target_resource_version),
                    edge_type=FEEDBACK_EDGE,
                    weight=1.0,
                )
        # Feedback text is an exact behavior signal, not a preferred copy snapshot.
        # PreferenceLearningService records it actor-privately and rebuilds the private
        # profile in this same transaction; failures must roll the feedback write back.
        from data_foundation.preference_learning import PreferenceLearningService

        PreferenceLearningService(repo).record_exact_event(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            event_type=feedback_type,
            source_resource_id=str(resource.id),
            source_resource_version=int(resource.version),
            source_event_id=f"feedback-request:{stable_request}",
            event_payload={
                "feedback": feedback,
                "feedback_type": feedback_type,
                "target_resource_id": target_resource_id,
                "target_resource_version": target_resource_version,
            },
        )
    result = _payload(resource, [])
    result["idempotent_replay"] = idempotent_replay
    return result


def _clean_strings(values: list[str], *, field: str) -> list[str]:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not cleaned:
        raise ValueError(f"{field} must contain at least one non-empty string")
    return cleaned


def _clean_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        resource_id = item.get("resource_id")
        if not isinstance(resource_id, str) or not resource_id.strip():
            continue
        resource_id = resource_id.strip()
        resource_version = item.get("resource_version")
        if (
            not isinstance(resource_version, int)
            or isinstance(resource_version, bool)
            or resource_version <= 0
        ):
            continue
        identity = (resource_id, resource_version)
        if identity in seen:
            continue
        seen.add(identity)
        cleaned_item = {
            "resource_id": resource_id,
            "resource_version": resource_version,
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
    generated_version: int,
    evidence: list[dict[str, Any]],
) -> None:
    for item in evidence:
        target = item["resource_id"]
        target_version = int(item["resource_version"])
        # evidence resource_id 是用户/LLM 提供的不可信输入:只对 actor 可读的 target 建 derived_from
        # 边,跳过无权读的(防越权连到他人私有资源),与 _clean_evidence「丢坏的、继续」一致。
        if not _actor_can_read(
            repo, tenant_id=tenant_id, actor_open_id=actor_open_id, target_resource_id=target,
            target_resource_version=target_version,
        ):
            continue
        repo.add_edge(
            tenant_id=tenant_id,
            source_resource_id=generated_id,
            source_resource_version=generated_version,
            target_resource_id=target,
            target_resource_version=target_version,
            edge_type=DERIVED_EDGE,
            weight=1.0,
        )


def _link_copy_versions(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    copy_resource_id: str,
    candidate_versions: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    reference_resource_id: str | None,
    reference_resource_version: int | None,
    source_topic: str | None,
) -> None:
    """Give every immutable copy candidate its own exact provenance edges."""
    exact_reference_version = None
    if reference_resource_id:
        exact_reference_version = _required_version(
            reference_resource_version, field="reference_resource_version"
        )
    ensure_link = getattr(repo, "ensure_resource_association", None)
    for candidate in candidate_versions:
        version = _required_version(
            candidate.get("resource_version"), field="candidate resource_version"
        )
        _link_evidence(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            generated_id=copy_resource_id,
            generated_version=version,
            evidence=evidence,
        )
        if reference_resource_id and exact_reference_version is not None:
            link_imitation_source(
                repo,
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                copy_resource_id=copy_resource_id,
                copy_resource_version=version,
                reference_resource_id=reference_resource_id,
                reference_resource_version=exact_reference_version,
            )
        # Strong provenance wins; without one, attach the exact candidate to a weak
        # existing neighbour so B/C candidates do not become version-level islands.
        if callable(ensure_link):
            ensure_link(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=copy_resource_id,
                resource_version=version,
                source_topic=source_topic,
            )


def associate_ingested_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_id: str,
    resource_version: int,
    neighbors: list[dict[str, Any]],
    co_ingested_resources: list[dict[str, Any]] | None = None,
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
    resource_version = _required_version(resource_version, field="resource_version")
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
        target_version = item.get("resource_version")
        if (
            not isinstance(target_version, int)
            or isinstance(target_version, bool)
            or target_version <= 0
        ):
            continue
        if target == resource_id or target in linked:
            continue
        if not _actor_can_read(
            repo, tenant_id=tenant_id, actor_open_id=actor_open_id, target_resource_id=target,
            target_resource_version=target_version,
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
            source_resource_version=resource_version,
            target_resource_id=target,
            target_resource_version=target_version,
            edge_type=SEMANTIC_EDGE,
            weight=weight,
        )
        linked.add(target)
        n_semantic += 1

    n_co = 0
    if n_semantic == 0:
        # 语义/主题关联一条都没建成 → 行为兜底:同批收录的其它素材互挂 co_ingested。
        for item in co_ingested_resources or []:
            if not isinstance(item, dict):
                continue
            other = item.get("resource_id")
            other_version = item.get("resource_version")
            if (
                not isinstance(other, str)
                or not other.strip()
                or not isinstance(other_version, int)
                or isinstance(other_version, bool)
                or other_version <= 0
            ):
                continue
            other = other.strip()
            if other == resource_id or other in linked:
                continue
            # 同批伙伴是本次同一入库动作产生的资源,同 actor 同 tenant,天然可读;
            # 仍走 add_edge 的 tenant 端点校验(FeedbackRepository 内)兜底。
            repo.add_edge(
                tenant_id=tenant_id,
                source_resource_id=resource_id,
                source_resource_version=resource_version,
                target_resource_id=other,
                target_resource_version=other_version,
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
    copy_resource_version: int,
    reference_resource_id: str,
    reference_resource_version: int,
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
    copy_resource_version = _required_version(
        copy_resource_version, field="copy_resource_version"
    )
    reference_resource_version = _required_version(
        reference_resource_version, field="reference_resource_version"
    )
    if not reference_resource_id or reference_resource_id == copy_resource_id:
        return False
    if not _actor_can_read(
        repo, tenant_id=tenant_id, actor_open_id=actor_open_id,
        target_resource_id=reference_resource_id,
        target_resource_version=reference_resource_version,
    ):
        return False
    repo.add_edge(
        tenant_id=tenant_id,
        source_resource_id=copy_resource_id,
        source_resource_version=copy_resource_version,
        target_resource_id=reference_resource_id,
        target_resource_version=reference_resource_version,
        edge_type=IMITATED_EDGE,
        weight=1.0,
    )
    return True


def _payload(resource: Any, evidence: list[dict[str, Any]]) -> dict[str, Any]:
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


def _required_version(value: Any, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _unit_of_work(repo: Any):
    unit_of_work = getattr(repo, "unit_of_work", None)
    return unit_of_work() if callable(unit_of_work) else nullcontext()
