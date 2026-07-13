"""Exact-version knowledge ingestion built on the existing resource outbox."""

from data_foundation.knowledge.models import KnowledgeDecision, KnowledgeSnapshot
from data_foundation.knowledge.normalizer import normalize_knowledge_text, normalized_hash
from data_foundation.knowledge.policy import classify_knowledge_asset
from data_foundation.knowledge.repository import KnowledgeRepository
from data_foundation.knowledge.service import KnowledgeService

__all__ = [
    "KnowledgeDecision",
    "KnowledgeSnapshot",
    "KnowledgeRepository",
    "KnowledgeService",
    "classify_knowledge_asset",
    "normalize_knowledge_text",
    "normalized_hash",
]
