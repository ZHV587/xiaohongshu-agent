"""统一知识检索的公开证据契约。

检索层只返回已经通过 Postgres 当前知识指针与 ACL 裁决的精确资源版本。调用方不需要
理解 pgvector、Meilisearch 或 FalkorDB 的内部结果，也不能凭 ``resource_id`` 猜测最新
版本。四态 ``retrieval_mode`` 描述本次实际可用的主召回路径；引擎故障单独记录在
``degraded_engines``，避免把“引擎不可用”误报成“知识库没有相关内容”。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_foundation.writing_context import normalize_account_id


RetrievalMode = Literal[
    "hybrid",
    "semantic_only",
    "keyword_only",
    "insufficient_relevance",
]
RecallEngine = Literal["semantic", "keyword", "graph"]
RetrievalSource = Literal["semantic", "keyword", "graph"]


class RetrievalFilters(BaseModel):
    """用户可控的知识过滤条件；最终裁决始终在 Postgres 中重做一次。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_kinds: list[str] = Field(default_factory=list, max_length=20)
    source_kinds: list[str] = Field(default_factory=list, max_length=20)
    niches: list[str] = Field(default_factory=list, max_length=20)
    account_ids: list[str] = Field(default_factory=list, max_length=20)
    min_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    updated_after: datetime | None = None

    @field_validator("asset_kinds", "source_kinds", "niches")
    @classmethod
    def _normalize_terms(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = str(raw).strip()
            if not value:
                raise ValueError("filter values must be non-empty strings")
            if value not in seen:
                normalized.append(value)
                seen.add(value)
        return normalized

    @field_validator("account_ids")
    @classmethod
    def _normalize_account_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in values:
            value = normalize_account_id(raw)
            assert value is not None
            if value not in normalized:
                normalized.append(value)
        return normalized

    @field_validator("updated_after")
    @classmethod
    def _normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class EngineDegradation(BaseModel):
    """不携带底层异常文本的安全降级说明。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: RecallEngine
    reason_code: str = Field(min_length=1, max_length=120)
    retryable: bool = True

    @field_validator("reason_code")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason_code is required")
        return value


class EvidenceItem(BaseModel):
    """一条可引用证据；所有分数均已归一化到 ``[0, 1]``。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_id: str = Field(min_length=1)
    resource_version: int = Field(
        gt=0,
        strict=True,
        description="不可变资源版本，必须与 resource_id 成对使用",
    )
    type: str = Field(min_length=1)
    asset_kind: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    niche: str | None = None
    title: str
    summary: str
    source_updated_at: str = Field(
        description='源端更新时间；未知写“未知”，不得用本地 updated_at 冒充',
    )
    indexed_at: str = Field(description='知识索引时间；未知写“未知”')
    score: float = Field(ge=0.0, le=1.0, description="最终精排分")
    relevance: float = Field(ge=0.0, le=1.0, description="weighted RRF 相关度")
    freshness: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)
    performance: float = Field(ge=0.0, le=1.0)
    retrieval_sources: list[RetrievalSource] = Field(min_length=1, max_length=3)
    why_selected: str = Field(min_length=1)

    @field_validator("resource_id", "type", "asset_kind", "source_kind", "why_selected")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required text must not be blank")
        return value

    @field_validator("niche")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("source_updated_at", "indexed_at")
    @classmethod
    def _validate_evidence_timestamp(cls, value: str) -> str:
        value = value.strip()
        if value == "未知":
            return value
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("evidence timestamps must be ISO 8601 or 未知") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("evidence timestamps must include a timezone")
        return value

    @field_validator("retrieval_sources")
    @classmethod
    def _deduplicate_sources(cls, values: list[RetrievalSource]) -> list[RetrievalSource]:
        if len(values) != len(set(values)):
            raise ValueError("retrieval_sources must not contain duplicates")
        return values


class EvidencePackage(BaseModel):
    """统一检索结果；只有本对象中的 exact identity 才能继续读取正文。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retrieval_mode: RetrievalMode
    evidence: list[EvidenceItem] = Field(default_factory=list)
    engines_used: list[RecallEngine] = Field(default_factory=list, max_length=3)
    degraded_engines: list[EngineDegradation] = Field(default_factory=list, max_length=3)
    gaps: str | None = None

    @model_validator(mode="after")
    def _check_mode_contract(self) -> "EvidencePackage":
        used = set(self.engines_used)
        if len(used) != len(self.engines_used):
            raise ValueError("engines_used must not contain duplicates")
        degraded = [item.engine for item in self.degraded_engines]
        if len(degraded) != len(set(degraded)):
            raise ValueError("degraded_engines must not contain duplicate engines")
        if used.intersection(degraded):
            raise ValueError("an engine cannot be both used and degraded")

        if self.retrieval_mode == "insufficient_relevance":
            if self.evidence:
                raise ValueError("insufficient_relevance requires empty evidence")
            if not (self.gaps and self.gaps.strip()):
                raise ValueError("insufficient_relevance requires a non-empty gaps explanation")
            return self

        if not self.evidence:
            raise ValueError("a successful retrieval mode requires non-empty evidence")
        evidence_sources = {
            source for item in self.evidence for source in item.retrieval_sources
        }
        if evidence_sources != used:
            raise ValueError("engines_used must equal the evidence retrieval sources")
        primary_sources = evidence_sources & {"semantic", "keyword"}
        if self.retrieval_mode == "hybrid" and primary_sources != {
            "semantic",
            "keyword",
        }:
            raise ValueError("hybrid requires semantic and keyword evidence")
        if self.retrieval_mode == "semantic_only" and (
            primary_sources != {"semantic"}
        ):
            raise ValueError("semantic_only requires only semantic primary evidence")
        if self.retrieval_mode == "keyword_only" and (
            primary_sources != {"keyword"}
        ):
            raise ValueError("keyword_only requires only keyword primary evidence")
        return self


__all__ = [
    "EngineDegradation",
    "EvidenceItem",
    "EvidencePackage",
    "RecallEngine",
    "RetrievalFilters",
    "RetrievalMode",
    "RetrievalSource",
]
