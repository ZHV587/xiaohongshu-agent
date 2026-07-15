"""知识库统一检索领域服务。

唯一安全顺序是：双路召回 -> Postgres 当前知识/ACL/过滤门 -> 可选图一跳 -> 再过同一
Postgres 门 -> exact performance 精排。Meilisearch/FalkorDB 中的数据永远不能绕过
Postgres 成为证据。本模块同时承载 embedding 查询 profile 与 provider 调用，工具层只负责
解析 LangGraph 身份并调用 ``retrieve_for_actor``。
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
import logging
import math
import re
from typing import Any, Protocol
import uuid

import httpx

logger = logging.getLogger(__name__)

from data_foundation.config import (
    current_keyword_relevance_floor,
    current_relevance_floor,
    embedding_snapshot_for_version,
    resolve_query_instruction,
)
from data_foundation.evidence import (
    EngineDegradation,
    EvidenceItem,
    EvidencePackage,
    RecallEngine,
    RetrievalFilters,
)
from data_foundation.processors.embedding import (
    EmbeddingProviderConfig,
    embedding_config_from_snapshot,
)
from data_foundation.search import semantic_search
from data_foundation.search_ranker import (
    DEFAULT_KEYWORD_RELEVANCE_FLOOR,
    RecallHit,
    rank_knowledge_candidates,
    weighted_rrf_order,
)
from data_foundation.retrieval_policy import (
    RetrievalTask,
    graph_edge_types,
    select_task_bundle,
    validate_retrieval_task,
)
from data_foundation.reranker_shadow import execute_shadow_rerank


class RetrievalEngineUnavailable(RuntimeError):
    """一个可独立降级的召回引擎当前不可用。"""

    def __init__(self, reason_code: str):
        self.reason_code = _safe_reason_code(reason_code)
        super().__init__(self.reason_code)


class EmbeddingSearchUnavailable(RetrievalEngineUnavailable):
    """embedding 查询 profile/provider 不可用。"""


class RetrievalSecurityGateError(RuntimeError):
    """Postgres 资格或 ACL 裁决失败；调用方必须整体 fail closed。"""

    reason_code = "POSTGRES_KNOWLEDGE_GATE_FAILED"

    def __init__(self) -> None:
        super().__init__(self.reason_code)


class SemanticRecall(Protocol):
    def __call__(
        self,
        *,
        query: str,
        tenant_id: str,
        actor_open_id: str,
        limit: int,
    ) -> Sequence[Any]: ...


class KeywordRecall(Protocol):
    def __call__(
        self,
        *,
        query: str,
        tenant_id: str,
        limit: int,
        filters: Mapping[str, Any],
    ) -> Sequence[Any]: ...


class GraphExpand(Protocol):
    def __call__(
        self,
        *,
        tenant_id: str,
        resource_ids: list[str],
        resource_versions: list[int],
        edge_types: list[str],
    ) -> Any: ...


class KnowledgeGateRepository(Protocol):
    def current_knowledge_rows(self, **kwargs: Any) -> list[dict[str, Any]]: ...

    def bulk_exact_performance_metrics(
        self, **kwargs: Any
    ) -> dict[tuple[str, int], list[dict[str, Any]]]: ...


def _safe_reason_code(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9_]+", "_", str(value).strip().upper()).strip("_")
    return (normalized or "ENGINE_UNAVAILABLE")[:120]


def _generic_failure_code(engine: RecallEngine, exc: Exception) -> str:
    # 只暴露异常类型，不回传可能含 URL、token 或查询正文的异常消息。
    exception_name = re.sub(r"[^A-Za-z0-9]+", "_", type(exc).__name__).upper()
    return _safe_reason_code(f"{engine}_query_failed_{exception_name}")


def embedding_query_config_for_index(active_index: Any) -> EmbeddingProviderConfig:
    """从 active embedding index 的不可变 config_version 恢复查询 provider。"""

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
        raise EmbeddingSearchUnavailable(
            provider_config.reason_code or "EMBEDDING_QUERY_CONFIG_INVALID"
        )
    if (
        provider_config.model != active_index.embedding_model
        or provider_config.dimensions != active_index.dimensions
    ):
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_PROFILE_MISMATCH")
    return provider_config


def embed_query(
    query: str,
    *,
    config: EmbeddingProviderConfig,
    query_instruction: str | None,
    post: Callable[..., Any] | None = None,
) -> list[float]:
    """调用 OpenAI-compatible embeddings endpoint；不记录请求或密钥。"""

    text = query if not query_instruction else query_instruction.format(query=query)
    sender = post or httpx.post
    response = sender(
        config.base_url.rstrip("/") + "/embeddings",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json={"model": config.model, "input": [text], "dimensions": config.dimensions},
        timeout=config.timeout_seconds,
    )
    if response.status_code in {401, 403}:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_UNAUTHORIZED")
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", []) if isinstance(payload, Mapping) else []
    if len(data) != 1 or not isinstance(data[0], Mapping):
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_BAD_RESPONSE")
    raw_embedding = data[0].get("embedding")
    if not isinstance(raw_embedding, list) or len(raw_embedding) != config.dimensions:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_BAD_DIMENSIONS")
    try:
        vector = [float(value) for value in raw_embedding]
    except (TypeError, ValueError) as exc:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_BAD_VECTOR") from exc
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_BAD_VECTOR")
    return vector


class PgVectorSemanticRecall:
    def __init__(
        self,
        repo: Any,
        *,
        query_embedder: Callable[..., list[float]] = embed_query,
    ) -> None:
        self.repo = repo
        self.query_embedder = query_embedder

    def __call__(
        self,
        *,
        query: str,
        tenant_id: str,
        actor_open_id: str,
        limit: int,
    ) -> Sequence[Any]:
        active_index = self.repo.active_embedding_index(tenant_id)
        if active_index is None:
            raise EmbeddingSearchUnavailable("NO_ACTIVE_EMBEDDING_INDEX")
        provider = embedding_query_config_for_index(active_index)
        instruction = resolve_query_instruction(provider.model)
        vector = self.query_embedder(
            query,
            config=provider,
            query_instruction=instruction,
        )
        return semantic_search(
            self.repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            embedding=vector,
            embedding_model=active_index.embedding_model,
            top_k=limit,
        )


class MeiliKeywordRecall:
    def __init__(self, index: Any) -> None:
        self.index = index

    def __call__(
        self,
        *,
        query: str,
        tenant_id: str,
        limit: int,
        filters: Mapping[str, Any],
    ) -> Sequence[Any]:
        return self.index.search(
            query,
            tenant_id=tenant_id,
            limit=limit,
            filters=filters,
        )


class FalkorGraphExpand:
    def __init__(self, graph: Any) -> None:
        self.graph = graph

    def __call__(
        self,
        *,
        tenant_id: str,
        resource_ids: list[str],
        resource_versions: list[int],
        edge_types: list[str],
    ) -> Any:
        return self.graph.expand(
            resource_ids=resource_ids,
            resource_versions=resource_versions,
            edge_types=edge_types,
            tenant_id=tenant_id,
        )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _coerce_recall_hit(value: Any) -> RecallHit | None:
    if isinstance(value, RecallHit):
        return value
    metadata = _field(value, "metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    resource_id = _field(value, "resource_id")
    resource_version = _field(value, "resource_version", metadata.get("resource_version"))
    score = _field(value, "score", 0.0)
    try:
        return RecallHit(
            resource_id=str(resource_id),
            resource_version=resource_version,
            score=float(score),
        )
    except (TypeError, ValueError, AttributeError):
        # 外部索引中的坏文档不是证据；跳过后仍要由 PG 对其余候选逐条裁决。
        return None


def _normalize_hits(values: Sequence[Any], *, semantic_floor: float | None) -> list[RecallHit]:
    hits: list[RecallHit] = []
    seen: set[tuple[str, int]] = set()
    for value in values:
        hit = _coerce_recall_hit(value)
        if hit is None or hit.identity in seen:
            continue
        if semantic_floor is not None and hit.score < semantic_floor:
            continue
        hits.append(hit)
        seen.add(hit.identity)
    return hits


def _edge_value(edge: Any, name: str, default: Any = None) -> Any:
    aliases = {
        "source_resource_id": ("source_resource_id", "source"),
        "target_resource_id": ("target_resource_id", "target"),
        "source_resource_version": ("source_resource_version",),
        "target_resource_version": ("target_resource_version",),
        "weight": ("weight",),
    }
    for alias in aliases[name]:
        value = _field(edge, alias, None)
        if value is not None:
            return value
    return default


def _normalize_graph_hits(raw: Any, *, seeds: set[tuple[str, int]]) -> list[RecallHit]:
    # 单测或自定义实现可直接返回 RecallHit 序列。
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, tuple)):
        direct = _normalize_hits(raw, semantic_floor=None)
        if direct:
            return [hit for hit in direct if hit.identity not in seeds]

    if hasattr(raw, "edges"):
        edges = raw.edges
    elif isinstance(raw, tuple) and len(raw) == 2:
        _nodes, edges = raw
    elif isinstance(raw, Mapping):
        edges = raw.get("edges", [])
    else:
        return []

    weights: dict[tuple[str, int], float] = {}
    for edge in edges:
        try:
            source = (
                str(uuid.UUID(str(_edge_value(edge, "source_resource_id")))),
                int(_edge_value(edge, "source_resource_version")),
            )
            target = (
                str(uuid.UUID(str(_edge_value(edge, "target_resource_id")))),
                int(_edge_value(edge, "target_resource_version")),
            )
            weight = float(_edge_value(edge, "weight", 1.0))
        except (TypeError, ValueError, AttributeError):
            continue
        if not math.isfinite(weight):
            continue
        neighbor: tuple[str, int] | None = None
        if source in seeds and target not in seeds:
            neighbor = target
        elif target in seeds and source not in seeds:
            neighbor = source
        if neighbor is not None:
            weights[neighbor] = max(weights.get(neighbor, 0.0), min(max(weight, 0.0), 1.0))

    ordered = sorted(weights, key=lambda identity: (-weights[identity], identity))
    return [RecallHit(identity[0], identity[1], weights[identity]) for identity in ordered]


class RetrievalService:
    """通过依赖注入组合召回引擎，便于无外部服务的确定性单测。"""

    def __init__(
        self,
        repo: KnowledgeGateRepository,
        *,
        semantic_recall: SemanticRecall | None,
        keyword_recall: KeywordRecall | None,
        graph_expand: GraphExpand | None = None,
        relevance_floor: float = 0.50,
        keyword_relevance_floor: float = DEFAULT_KEYWORD_RELEVANCE_FLOOR,
        unavailable_reasons: Mapping[RecallEngine, str] | None = None,
        shadow_reranker: Callable[..., Sequence[Any]] | None = None,
        shadow_observer: Callable[..., Any] | None = None,
    ) -> None:
        if not 0.0 <= float(relevance_floor) <= 1.0:
            raise ValueError("relevance_floor must be between 0 and 1")
        if not 0.0 <= float(keyword_relevance_floor) <= 1.0:
            raise ValueError("keyword_relevance_floor must be between 0 and 1")
        self.repo = repo
        self.semantic_recall = semantic_recall
        self.keyword_recall = keyword_recall
        self.graph_expand = graph_expand
        self.relevance_floor = float(relevance_floor)
        self.keyword_relevance_floor = float(keyword_relevance_floor)
        self.unavailable_reasons = dict(unavailable_reasons or {})
        self.shadow_reranker = shadow_reranker
        self.shadow_observer = shadow_observer

    def _degradation(
        self, engine: RecallEngine, exc: Exception | None = None
    ) -> EngineDegradation:
        if isinstance(exc, RetrievalEngineUnavailable):
            reason = exc.reason_code
        elif exc is not None:
            reason = _generic_failure_code(engine, exc)
        else:
            reason = self.unavailable_reasons.get(engine, f"{engine}_not_configured")
        return EngineDegradation(engine=engine, reason_code=reason, retryable=True)

    def _gate(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        identities: Sequence[tuple[str, int]],
        filters: RetrievalFilters,
    ) -> list[dict[str, Any]]:
        if not identities:
            return []
        try:
            return self.repo.current_knowledge_rows(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_ids=[identity[0] for identity in identities],
                resource_versions=[identity[1] for identity in identities],
                asset_kinds=filters.asset_kinds,
                source_kinds=filters.source_kinds,
                niches=filters.niches,
                account_ids=filters.account_ids,
                min_quality=filters.min_quality,
                updated_after=filters.updated_after,
            )
        except Exception as exc:
            raise RetrievalSecurityGateError() from exc

    @staticmethod
    def _mode(evidence: Sequence[EvidenceItem]) -> str:
        primary = {
            source
            for item in evidence
            for source in item.retrieval_sources
            if source in {"semantic", "keyword"}
        }
        if primary == {"semantic", "keyword"}:
            return "hybrid"
        if primary == {"semantic"}:
            return "semantic_only"
        if primary == {"keyword"}:
            return "keyword_only"
        return "insufficient_relevance"

    def retrieve(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        query: str,
        limit: int = 10,
        filters: RetrievalFilters | Mapping[str, Any] | None = None,
        task_type: str | None = None,
    ) -> EvidencePackage:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        query = query.strip()
        if not query:
            raise ValueError("query is required")
        if not tenant_id or not actor_open_id:
            raise ValueError("tenant_id and actor_open_id are required")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise TypeError("limit must be an integer")
        safe_limit = min(max(int(limit), 1), 20)
        task = validate_retrieval_task(task_type, query=query)
        over_fetch = min(max(safe_limit * 5, 25), 200)
        if filters is None:
            selected_filters = RetrievalFilters()
        elif isinstance(filters, RetrievalFilters):
            selected_filters = filters
        else:
            selected_filters = RetrievalFilters.model_validate(filters)
        filter_payload = selected_filters.model_dump(mode="json", exclude_none=True)
        keyword_filter_payload = dict(filter_payload)
        # account ownership is an exact-version PostgreSQL fact and is intentionally
        # not copied to the external keyword index. Meili only narrows recall; PG is
        # the authoritative anti-cross-account gate below.
        keyword_filter_payload.pop("account_ids", None)

        successful_engines: list[RecallEngine] = []
        degraded: list[EngineDegradation] = []

        semantic_hits: list[RecallHit] = []
        if self.semantic_recall is None:
            degraded.append(self._degradation("semantic"))
        else:
            try:
                raw_semantic = self.semantic_recall(
                    query=query,
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    limit=over_fetch,
                )
                semantic_hits = _normalize_hits(
                    raw_semantic, semantic_floor=self.relevance_floor
                )
                successful_engines.append("semantic")
            except Exception as exc:
                degraded.append(self._degradation("semantic", exc))

        keyword_hits: list[RecallHit] = []
        if self.keyword_recall is None:
            degraded.append(self._degradation("keyword"))
        else:
            try:
                raw_keyword = self.keyword_recall(
                    query=query,
                    tenant_id=tenant_id,
                    limit=over_fetch,
                    filters=keyword_filter_payload,
                )
                keyword_hits = _normalize_hits(raw_keyword, semantic_floor=None)
                # Meili 原始分必须先过绝对门；之后的 RRF 还会乘原始分，低分 rank-1
                # 不再被归一化成 relevance=1。
                keyword_hits = [
                    hit
                    for hit in keyword_hits
                    if hit.score >= self.keyword_relevance_floor
                ]
                successful_engines.append("keyword")
            except Exception as exc:
                degraded.append(self._degradation("keyword", exc))

        primary_order = weighted_rrf_order(
            semantic_hits=semantic_hits,
            keyword_hits=keyword_hits,
            active_sources=[
                engine
                for engine in successful_engines
                if engine in {"semantic", "keyword"}
            ],
        )
        primary_rows = self._gate(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            identities=primary_order,
            filters=selected_filters,
        )
        allowed_primary = {
            (str(row["resource_id"]), int(row["resource_version"]))
            for row in primary_rows
        }
        semantic_hits = [hit for hit in semantic_hits if hit.identity in allowed_primary]
        keyword_hits = [hit for hit in keyword_hits if hit.identity in allowed_primary]

        graph_hits: list[RecallHit] = []
        graph_rows: list[dict[str, Any]] = []
        seed_order = weighted_rrf_order(
            semantic_hits=semantic_hits,
            keyword_hits=keyword_hits,
            active_sources=[
                engine
                for engine in successful_engines
                if engine in {"semantic", "keyword"}
            ],
        )[: min(safe_limit, 5)]
        if seed_order:
            if self.graph_expand is None:
                degraded.append(self._degradation("graph"))
            else:
                try:
                    raw_graph = self.graph_expand(
                        tenant_id=tenant_id,
                        resource_ids=[identity[0] for identity in seed_order],
                        resource_versions=[identity[1] for identity in seed_order],
                        edge_types=graph_edge_types(task),
                    )
                    graph_hits = _normalize_graph_hits(raw_graph, seeds=set(seed_order))
                    graph_hits = graph_hits[: min(safe_limit * 2, 20)]
                    successful_engines.append("graph")
                    graph_rows = self._gate(
                        tenant_id=tenant_id,
                        actor_open_id=actor_open_id,
                        identities=[hit.identity for hit in graph_hits],
                        filters=selected_filters,
                    )
                    allowed_graph = {
                        (str(row["resource_id"]), int(row["resource_version"]))
                        for row in graph_rows
                    }
                    graph_hits = [hit for hit in graph_hits if hit.identity in allowed_graph]
                except RetrievalSecurityGateError:
                    raise
                except Exception as exc:
                    graph_hits = []
                    graph_rows = []
                    degraded.append(self._degradation("graph", exc))

        rows_by_identity: dict[tuple[str, int], dict[str, Any]] = {}
        for row in [*primary_rows, *graph_rows]:
            identity = (str(row["resource_id"]), int(row["resource_version"]))
            rows_by_identity[identity] = row
        all_rows = list(rows_by_identity.values())
        all_identities = list(rows_by_identity)

        if not all_identities:
            return EvidencePackage(
                retrieval_mode="insufficient_relevance",
                evidence=[],
                engines_used=successful_engines,
                degraded_engines=degraded,
                gaps="当前知识库没有通过相关度、权限与过滤条件的证据",
            )

        try:
            performance = self.repo.bulk_exact_performance_metrics(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_ids=[identity[0] for identity in all_identities],
                resource_versions=[identity[1] for identity in all_identities],
            )
        except Exception as exc:
            raise RetrievalSecurityGateError() from exc

        active_sources = [
            source
            for source, hits in (
                ("semantic", semantic_hits),
                ("keyword", keyword_hits),
                ("graph", graph_hits),
            )
            if hits
        ]
        ranked = rank_knowledge_candidates(
            rows=all_rows,
            semantic_hits=semantic_hits,
            keyword_hits=keyword_hits,
            graph_hits=graph_hits,
            active_sources=active_sources,
            performance_data=performance,
            limit=min(safe_limit * 3, 50),
        )
        ranked = select_task_bundle(ranked, task=task, limit=safe_limit)
        if not ranked:
            return EvidencePackage(
                retrieval_mode="insufficient_relevance",
                evidence=[],
                engines_used=successful_engines,
                degraded_engines=degraded,
                gaps="当前知识库没有足够相关的可用证据",
            )

        if self.shadow_reranker is not None:
            try:
                shadow = execute_shadow_rerank(
                    query=query,
                    ranked_candidates=ranked,
                    reranker=self.shadow_reranker,
                )
                if self.shadow_observer is not None:
                    self.shadow_observer(
                        tenant_id=tenant_id,
                        actor_open_id=actor_open_id,
                        task_type=task,
                        observation=shadow,
                    )
            except Exception as exc:  # noqa: BLE001 - 影子实验永不影响线上证据顺序
                logger.warning("reranker_shadow_failed type=%s", type(exc).__name__)

        evidence = []
        for item in ranked:
            payload = asdict(item)
            payload.pop("duplicate_family_id", None)
            payload["retrieval_sources"] = list(payload["retrieval_sources"])
            evidence.append(EvidenceItem.model_validate(payload))
        engines_used: list[RecallEngine] = []
        for engine in ("semantic", "keyword", "graph"):
            if any(engine in item.retrieval_sources for item in evidence):
                engines_used.append(engine)
        return EvidencePackage(
            retrieval_mode=self._mode(evidence),
            evidence=evidence,
            engines_used=engines_used,
            degraded_engines=degraded,
            gaps=None,
        )


def build_runtime_retrieval_service(repo: Any) -> RetrievalService:
    """按当前环境配置组装生产引擎；仍只使用 deepagents 工具调用的同步请求上下文。"""

    from data_foundation.engine_config import (
        falkor_config_from_env,
        meili_config_from_env,
    )
    from data_foundation.falkor_client import FalkorResourceGraph
    from data_foundation.meili_client import MeiliResourceIndex

    unavailable: dict[RecallEngine, str] = {}
    meili_config = meili_config_from_env()
    if meili_config.state == "enabled":
        keyword: KeywordRecall | None = MeiliKeywordRecall(
            MeiliResourceIndex.from_config(meili_config)
        )
    else:
        keyword = None
        unavailable["keyword"] = "MEILI_UNAVAILABLE"

    falkor_config = falkor_config_from_env()
    if falkor_config.state == "enabled":
        graph: GraphExpand | None = FalkorGraphExpand(
            FalkorResourceGraph.from_config(falkor_config)
        )
    else:
        graph = None
        unavailable["graph"] = "FALKOR_UNAVAILABLE"

    return RetrievalService(
        repo,
        semantic_recall=PgVectorSemanticRecall(repo),
        keyword_recall=keyword,
        graph_expand=graph,
        relevance_floor=current_relevance_floor(),
        keyword_relevance_floor=current_keyword_relevance_floor(),
        unavailable_reasons=unavailable,
    )


def retrieve_for_actor(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    query: str,
    limit: int = 10,
    filters: RetrievalFilters | Mapping[str, Any] | None = None,
    task_type: str | None = None,
) -> EvidencePackage:
    """工具、在线采用流程与脚本共用的生产领域入口。"""

    return build_runtime_retrieval_service(repo).retrieve(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        query=query,
        limit=limit,
        filters=filters,
        task_type=task_type,
    )


__all__ = [
    "EmbeddingSearchUnavailable",
    "FalkorGraphExpand",
    "MeiliKeywordRecall",
    "PgVectorSemanticRecall",
    "RetrievalEngineUnavailable",
    "RetrievalSecurityGateError",
    "RetrievalService",
    "build_runtime_retrieval_service",
    "embed_query",
    "embedding_query_config_for_index",
    "retrieve_for_actor",
]
