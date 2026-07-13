from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Eligibility = Literal["pending", "qualified", "rejected"]


@dataclass(frozen=True)
class KnowledgeSnapshot:
    tenant_id: str
    resource_id: str
    resource_version: int
    resource_type: str
    status: str
    visibility: str
    owner_open_id: str | None
    title: str
    content_text: str
    content_json: dict[str, Any]
    lifecycle_status: str | None = None
    lifecycle_state_version: int | None = None
    knowledge_target_version: int | None = None
    mapping_systems: tuple[str, ...] = ()
    confirmation_metadata: dict[str, Any] | None = None
    synthesis_family_count: int = 0
    teardown_source_count: int = 0


@dataclass(frozen=True)
class KnowledgeDecision:
    eligibility: Eligibility
    asset_kind: str
    source_kind: str
    source_authority: dict[str, Any]
    quality_score: float
    eligible_for_synthesis: bool
    reason_code: str


@dataclass(frozen=True)
class KnowledgeEnrichResult:
    status: Literal["qualified", "rejected", "superseded"]
    resource_id: str
    resource_version: int
    family_id: str | None = None
    duplicate_kind: str | None = None
    downstream_topics: tuple[str, ...] = ()
