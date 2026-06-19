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
