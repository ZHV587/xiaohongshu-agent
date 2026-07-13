from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Resource:
    id: str
    tenant_id: str
    type: str
    title: str
    summary: str | None
    content_text: str | None
    content_json: dict[str, Any]
    status: str
    visibility: str
    owner_open_id: str | None
    created_at: datetime
    updated_at: datetime
    source_updated_at: datetime | None = None
    version: int | None = None


@dataclass(frozen=True)
class ResourceSearchResult:
    resource_id: str
    title: str
    summary: str | None
    score: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class GraphNode:
    resource_id: str
    title: str
    type: str
    depth: int


@dataclass(frozen=True)
class GraphEdge:
    source_resource_id: str
    target_resource_id: str
    edge_type: str
    weight: float


@dataclass(frozen=True)
class GraphExpansion:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@dataclass(frozen=True)
class OutboxRequest:
    topic: str
    dedupe_parts: tuple[str, ...]
    payload: dict[str, Any]


@dataclass(frozen=True)
class OutboxItem:
    id: str
    tenant_id: str
    resource_id: str | None
    resource_version: int | None
    topic: str
    dedupe_key: str
    payload: dict[str, Any]
    status: str
    attempts: int
    next_attempt_at: datetime
    lease_owner: str | None
    lease_expires_at: datetime | None
    error_code: str | None
    error_summary: str | None
    dead_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SyncSource:
    id: str
    tenant_id: str
    source_type: str
    name: str
    external_id: str | None
    config: dict[str, Any]
    enabled: bool
    schedule_seconds: int
    next_run_at: datetime
    last_dispatched_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    cursor: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SourceSecrets:
    credentials: dict[str, Any]


@dataclass(frozen=True)
class EmbeddingIndex:
    id: str
    tenant_id: str
    embedding_model: str
    config_version: str
    dimensions: int
    chunker_version: str
    status: str
    expected_resources: int
    completed_resources: int
    failed_resources: int
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ServiceExecution:
    id: str
    component: str
    instance_id: str
    tenant_id: str | None
    operation: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    processed_count: int
    succeeded_count: int
    failed_count: int
    duration_ms: int | None
    error_code: str | None
    error_summary: str | None
    config_version: str | None


@dataclass(frozen=True)
class ProcessorState:
    topic: str
    status: str
    config_version: str | None
    reason_code: str | None


@dataclass(frozen=True)
class RuntimeIdentityConfig:
    tenant_id: str
    open_id: str


@dataclass(frozen=True)
class UserSkillVersion:
    id: str
    tenant_id: str
    owner_open_id: str
    skill_id: str
    version: int
    display_name: str
    description: str
    instructions_markdown: str
    trigger_examples: list[str]
    non_trigger_examples: list[str]
    tags: list[str]
    content_hash: str
    created_by_open_id: str
    created_at: datetime


@dataclass(frozen=True)
class UserSkill:
    id: str
    tenant_id: str
    owner_open_id: str
    runtime_name: str
    latest_version: int
    status: str
    published_version: int | None
    created_at: datetime
    updated_at: datetime
    latest_definition: UserSkillVersion


@dataclass(frozen=True)
class UserSkillAuditEvent:
    id: str
    tenant_id: str
    owner_open_id: str
    skill_id: str
    event_type: str
    actor_open_id: str
    skill_version: int | None
    payload: dict[str, Any]
    created_at: datetime
