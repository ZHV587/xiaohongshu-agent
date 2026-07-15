"""Deterministic writing-preference learning and cross-family pattern synthesis.

This module deliberately contains no LLM calls.  User lifecycle facts are converted
to actor-private observations, the whole observation set deterministically rebuilds a
private profile, and only motifs supported by at least three independent duplicate
families become qualified ``writing_pattern`` candidates.

Automatic trigger integration points (the lifecycle caller must pass the exact event
id returned by ``resource_events``):

* ``GeneratedCopyRepository.adopt_version`` -> ``record_exact_event(..., event_type="adopted")``
* ``finalize_for_schedule`` -> ``event_type="finalized_for_schedule"``
* ``mark_published`` -> ``event_type="published"``
* ``save_revision`` / schedule dirty-save -> ``event_type="revision_saved"`` and
  ``base_resource_version``
* performance backfill, after its exact metric version is committed ->
  ``event_type="metrics_backfilled"`` with the cleaned metric payload

Hooks are intentionally kept outside the generated-copy and performance repositories
so those transactions can adopt this service without creating a parallel agent loop.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence
import uuid

from data_foundation.outbox_requests import default_write_requests
from data_foundation.writing_context import (
    GLOBAL_SCOPE_KEY,
    WritingContext,
    context_from_payload,
)
from data_foundation.performance_scoring import normalize_performance


OBSERVATION_SCHEMA_VERSION = 1
PROFILE_SCHEMA_VERSION = 1
PATTERN_SCHEMA_VERSION = 1
MIN_PATTERN_FAMILIES = 3
MIN_PATTERN_QUALITY = 0.70
MIN_PATTERN_PERFORMANCE = 0.02
METRIC_SCORE_PIVOT = 0.05

_PROFILE_NAMESPACE = uuid.UUID("32534dcb-fb1d-4e51-96fd-58a51cde4a57")
_PATTERN_NAMESPACE = uuid.UUID("9860ae32-34bd-43c7-8a3c-d62af7577cae")
_EVENT_ALIASES = {
    "adopted": "adopted",
    "finalized": "finalized",
    "finalized_for_schedule": "finalized",
    "published": "published",
    "metric": "metric",
    "metrics_backfilled": "metric",
    "revision": "revision",
    "revision_saved": "revision",
    "feedback": "feedback",
    "user_feedback": "feedback",
    "revision_request": "feedback",
    "variant_selected": "comparison",
}
_EVENT_WEIGHTS = {
    "adopted": 2.0,
    "finalized": 3.0,
    "published": 4.0,
    "metric": 4.0,
    "revision": 2.0,
    "feedback": 1.0,
    "comparison": 0.0,
}
_PROFILE_DIMENSIONS = ("niche", "hook_type", "cta_type", "structure_type", "variant_label")
_PATTERN_DIMENSIONS = ("hook_type", "cta_type", "structure_type")
_VISIBILITY_RANK = {"private": 0, "team": 1}


@dataclass(frozen=True, order=True)
class ExactResourceVersion:
    resource_id: str
    resource_version: int

    def __post_init__(self) -> None:
        resource_id = self.resource_id.strip() if isinstance(self.resource_id, str) else ""
        if not resource_id:
            raise ValueError("resource_id is required")
        if (
            not isinstance(self.resource_version, int)
            or isinstance(self.resource_version, bool)
            or self.resource_version <= 0
        ):
            raise ValueError("resource_version must be a positive integer")
        object.__setattr__(self, "resource_id", resource_id)

    def payload(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "resource_version": self.resource_version,
        }


@dataclass(frozen=True)
class PreferenceObservation:
    event_key: str
    event_type: str
    source: ExactResourceVersion
    source_event_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeAsset:
    source: ExactResourceVersion
    duplicate_family_id: str
    visibility: str
    content_json: dict[str, Any]
    quality_score: float = 0.0
    performance_score: float | None = None
    normalized_hash: str | None = None

    def __post_init__(self) -> None:
        family = (
            self.duplicate_family_id.strip()
            if isinstance(self.duplicate_family_id, str)
            else ""
        )
        if not family:
            raise ValueError("duplicate_family_id is required")
        object.__setattr__(self, "duplicate_family_id", family)
        object.__setattr__(self, "visibility", normalize_visibility(self.visibility))
        score = float(self.quality_score)
        object.__setattr__(self, "quality_score", score if math.isfinite(score) else 0.0)
        performance = self.performance_score
        if performance is not None:
            performance = float(performance)
            if not math.isfinite(performance):
                performance = None
            else:
                performance = max(performance, 0.0)
        object.__setattr__(self, "performance_score", performance)
        digest = (
            self.normalized_hash.strip()
            if isinstance(self.normalized_hash, str) and self.normalized_hash.strip()
            else None
        )
        object.__setattr__(self, "normalized_hash", digest)


@dataclass(frozen=True)
class PatternCandidate:
    pattern_key: str
    dimension: str
    value: str
    visibility: str
    sources: tuple[KnowledgeAsset, ...]

    @property
    def source_family_ids(self) -> tuple[str, ...]:
        return tuple(source.duplicate_family_id for source in self.sources)


def canonical_json(value: Any) -> str:
    """Canonical UTF-8 JSON used by every idempotency/content digest."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def preference_event_key(
    *,
    event_type: str,
    source: ExactResourceVersion,
    source_event_id: str | None = None,
    event_payload: Mapping[str, Any] | None = None,
) -> str:
    """Build a stable event key; retries of one exact fact collapse to one row."""
    normalized_type = normalize_event_type(event_type)
    normalized_event_id = (
        source_event_id.strip() if isinstance(source_event_id, str) and source_event_id.strip() else None
    )
    identity = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "event_type": normalized_type,
        "source": source.payload(),
        "source_event_id": normalized_event_id,
        # Some import paths do not own a resource_events id.  In that case the exact
        # upstream payload is part of the identity instead of a random retry token.
        "event_payload": None if normalized_event_id else dict(event_payload or {}),
    }
    digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    return f"preference:v{OBSERVATION_SCHEMA_VERSION}:{digest}"


def normalize_event_type(event_type: str) -> str:
    cleaned = event_type.strip() if isinstance(event_type, str) else ""
    try:
        return _EVENT_ALIASES[cleaned]
    except KeyError as exc:
        raise ValueError(f"unsupported preference event type: {cleaned or '<empty>'}") from exc


def extract_writing_features(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Extract only deterministic, explainable writing features from one exact snapshot."""
    content = dict(snapshot or {})
    title = _text(content.get("title"))
    body = _text(content.get("body")) or _text(content.get("content_text"))
    tags = sorted({_text(tag) for tag in content.get("tags", []) if _text(tag)})
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\n", body) if part.strip()]
    style_tags = sorted(
        {
            _text(tag)
            for key in ("style_tags", "style_labels")
            for tag in _string_list(content.get(key))
            if _text(tag)
        }
    )
    return {
        "title_length": len(title),
        "body_length": len(body),
        "paragraph_count": len(paragraphs),
        "tag_count": len(tags),
        "tags": tags,
        "variant_label": _first_text(content, "variant_label", "label"),
        "niche": _first_text(content, "niche", "category", "vertical"),
        "hook_type": _first_text(content, "hook_type", "hook", "hook_mechanism")
        or _infer_hook_type(title),
        "cta_type": _first_text(content, "cta_type", "cta") or _infer_cta_type(body),
        "structure_type": _first_text(content, "structure_type", "structure", "format_type")
        or _infer_structure_type(paragraphs),
        "style_tags": style_tags,
    }


def build_preference_observation(
    *,
    event_type: str,
    source: ExactResourceVersion,
    snapshot: Mapping[str, Any],
    source_event_id: str | None = None,
    event_payload: Mapping[str, Any] | None = None,
    previous_snapshot: Mapping[str, Any] | None = None,
) -> PreferenceObservation:
    normalized_type = normalize_event_type(event_type)
    event_payload = dict(event_payload or {})
    # Explicit feedback is a signal resource, not an adopted writing sample.  Treating
    # "修改意见" as a preferred title/body would corrupt the length/style profile.
    features = {} if normalized_type == "feedback" else extract_writing_features(snapshot)
    signal: dict[str, Any] = {}
    if normalized_type == "revision":
        if previous_snapshot is None:
            raise ValueError("previous_snapshot is required for a revision observation")
        before = extract_writing_features(previous_snapshot)
        signal = _revision_signal(before=before, after=features)
        base_version = event_payload.get("base_version")
        try:
            base_source = ExactResourceVersion(source.resource_id, base_version)
        except ValueError:
            pass
        else:
            signal["exact_sources"] = [base_source.payload()]
    elif normalized_type == "metric":
        signal = _metric_signal(event_payload)
    elif normalized_type == "feedback":
        signal = _feedback_signal(event_payload, snapshot)
    elif normalized_type == "comparison":
        rejected_features = event_payload.get("rejected_features")
        signal = {
            "rejected_features": (
                dict(rejected_features)
                if isinstance(rejected_features, Mapping)
                else {}
            ),
            "chosen_ordinal": event_payload.get("chosen_ordinal"),
            "rejected_ordinal": event_payload.get("rejected_ordinal"),
            "exact_sources": [
                dict(event_payload["rejected_source"])
            ] if isinstance(event_payload.get("rejected_source"), Mapping) else [],
        }
    observation_payload = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "features": features,
        "signal": signal,
    }
    return PreferenceObservation(
        event_key=preference_event_key(
            event_type=normalized_type,
            source=source,
            source_event_id=source_event_id,
            event_payload=event_payload,
        ),
        event_type=normalized_type,
        source=source,
        source_event_id=(
            source_event_id.strip()
            if isinstance(source_event_id, str) and source_event_id.strip()
            else None
        ),
        payload=observation_payload,
    )


def rebuild_preference_profile(
    actor_open_id: str,
    observations: Iterable[PreferenceObservation],
) -> dict[str, Any]:
    """Rebuild a profile from the complete actor-private event set, independent of input order."""
    actor = actor_open_id.strip() if isinstance(actor_open_id, str) else ""
    if not actor:
        raise ValueError("actor_open_id is required")
    unique = {observation.event_key: observation for observation in observations}
    ordered = [unique[key] for key in sorted(unique)]
    event_counts = Counter(observation.event_type for observation in ordered)
    dimension_scores: dict[str, Counter[str]] = {
        dimension: Counter() for dimension in _PROFILE_DIMENSIONS
    }
    tag_scores: Counter[str] = Counter()
    style_scores: Counter[str] = Counter()
    numeric: dict[str, list[tuple[float, float]]] = defaultdict(list)
    source_set = {observation.source for observation in ordered}
    revision_counts: Counter[str] = Counter()
    feedback_traits: Counter[str] = Counter()
    metric_scores: list[float] = []
    eligible_metric_scores: list[float] = []
    avoid_dimension_scores: dict[str, Counter[str]] = {
        dimension: Counter() for dimension in _PROFILE_DIMENSIONS
    }
    avoid_tag_scores: Counter[str] = Counter()
    avoid_style_scores: Counter[str] = Counter()

    measured_source_factors: dict[ExactResourceVersion, list[float]] = defaultdict(list)
    for observation in ordered:
        if observation.event_type != "metric":
            continue
        signal = dict(observation.payload.get("signal") or {})
        measured_source_factors[observation.source].append(
            _metric_lifecycle_factor(signal)
        )
    source_outcome_factor = {
        source: sum(factors) / len(factors)
        for source, factors in measured_source_factors.items()
        if factors
    }

    for observation in ordered:
        weight = _observation_weight(observation)
        if observation.event_type in {"adopted", "finalized", "published"}:
            weight *= source_outcome_factor.get(observation.source, 1.0)
        features = dict(observation.payload.get("features") or {})
        # 低/零效果 metric 仍进入 outcome_summary，但不再把失败稿的写法强化为偏好。
        if weight > 0:
            for key in ("title_length", "body_length", "paragraph_count", "tag_count"):
                value = features.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric[key].append((float(value), weight))
            for dimension in _PROFILE_DIMENSIONS:
                value = _normalized_feature_value(features.get(dimension))
                if value:
                    dimension_scores[dimension][value] += weight
            for tag in _string_list(features.get("tags")):
                tag_scores[tag] += weight
            for tag in _string_list(features.get("style_tags")):
                style_scores[tag] += weight
        signal = dict(observation.payload.get("signal") or {})
        for related in signal.get("exact_sources", []):
            if not isinstance(related, Mapping):
                continue
            try:
                source_set.add(
                    ExactResourceVersion(
                        str(related.get("resource_id") or ""),
                        related.get("resource_version"),
                    )
                )
            except ValueError:
                continue
        if observation.event_type == "revision":
            for change in _string_list(signal.get("changed_fields")):
                revision_counts[f"changed:{change}"] += 1
            for field in ("title_length_delta", "body_length_delta", "paragraph_count_delta"):
                delta = signal.get(field)
                if isinstance(delta, (int, float)) and not isinstance(delta, bool) and delta != 0:
                    revision_counts[f"{field}:{'increase' if delta > 0 else 'decrease'}"] += 1
        if observation.event_type == "metric":
            score = signal.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score):
                metric_scores.append(float(score))
                if signal.get("learning_eligible") is True:
                    eligible_metric_scores.append(float(score))
                if signal.get("learning_eligible") is True and float(score) < MIN_PATTERN_PERFORMANCE:
                    for dimension in _PROFILE_DIMENSIONS:
                        value = _normalized_feature_value(features.get(dimension))
                        if value:
                            avoid_dimension_scores[dimension][value] += 1
                    for tag in _string_list(features.get("tags")):
                        avoid_tag_scores[tag] += 1
                    for tag in _string_list(features.get("style_tags")):
                        avoid_style_scores[tag] += 1
        if observation.event_type == "comparison":
            rejected = dict(signal.get("rejected_features") or {})
            bias_weight = _pairwise_bias_weight(signal)
            for dimension in _PROFILE_DIMENSIONS:
                value = _normalized_feature_value(rejected.get(dimension))
                if value:
                    avoid_dimension_scores[dimension][value] += bias_weight
            for tag in _string_list(rejected.get("tags")):
                avoid_tag_scores[tag] += bias_weight
            for tag in _string_list(rejected.get("style_tags")):
                avoid_style_scores[tag] += bias_weight
        if observation.event_type == "feedback":
            for trait in _string_list(signal.get("traits")):
                feedback_traits[trait] += 1

    sources = sorted(source_set)
    input_digest = hashlib.sha256(
        canonical_json([observation.event_key for observation in ordered]).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "actor_open_id": actor,
        "input_digest": input_digest,
        "observation_count": len(ordered),
        "source_count": len(sources),
        "event_counts": {event: event_counts.get(event, 0) for event in _EVENT_WEIGHTS},
        "preferred_ranges": {
            key: _weighted_range(values) for key, values in sorted(numeric.items())
        },
        "preferences": {
            **{
                dimension: _ranked_values(scores)
                for dimension, scores in dimension_scores.items()
            },
            "tags": _ranked_values(tag_scores),
            "style_tags": _ranked_values(style_scores),
        },
        "revision_tendencies": [
            {"signal": key, "count": count}
            for key, count in sorted(revision_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "explicit_feedback_traits": [
            {"trait": key, "count": count}
            for key, count in sorted(feedback_traits.items(), key=lambda item: (-item[1], item[0]))
        ],
        "avoid_preferences": {
            **{
                dimension: _ranked_values(scores)
                for dimension, scores in avoid_dimension_scores.items()
            },
            "tags": _ranked_values(avoid_tag_scores),
            "style_tags": _ranked_values(avoid_style_scores),
        },
        "outcome_summary": {
            "metric_observation_count": len(metric_scores),
            "evaluable_metric_count": len(eligible_metric_scores),
            "uncertain_metric_count": len(metric_scores) - len(eligible_metric_scores),
            "positive_metric_count": sum(
                1
                for score in eligible_metric_scores
                if score >= MIN_PATTERN_PERFORMANCE
            ),
            "low_metric_count": sum(
                1 for score in eligible_metric_scores if score < MIN_PATTERN_PERFORMANCE
            ),
            "average_score": round(
                sum(eligible_metric_scores) / len(eligible_metric_scores), 6
            )
            if eligible_metric_scores
            else None,
        },
        "sources": [source.payload() for source in sources],
    }


def synthesize_pattern_candidates(
    assets: Iterable[KnowledgeAsset],
    *,
    minimum_families: int = MIN_PATTERN_FAMILIES,
) -> list[PatternCandidate]:
    """Return repeated motifs supported by N independent current resources.

    Multiple copies in one duplicate family, equal normalized texts, and historical
    variants of one stable resource count once.  The best representative is selected
    deterministically by observed performance, quality, then exact identity.
    """
    if (
        not isinstance(minimum_families, int)
        or isinstance(minimum_families, bool)
        or minimum_families < MIN_PATTERN_FAMILIES
    ):
        raise ValueError(f"minimum_families must be >= {MIN_PATTERN_FAMILIES}")
    grouped: dict[tuple[str, str], list[KnowledgeAsset]] = defaultdict(list)
    for asset in assets:
        if asset.performance_score is None:
            if asset.quality_score < MIN_PATTERN_QUALITY:
                continue
        elif asset.performance_score < MIN_PATTERN_PERFORMANCE:
            continue
        for dimension, value in pattern_features(asset.content_json):
            grouped[(dimension, value)].append(asset)

    candidates: list[PatternCandidate] = []
    for (dimension, value), matching in sorted(grouped.items()):
        independent_groups = _independent_asset_groups(matching)
        if len(independent_groups) < minimum_families:
            continue
        representatives = tuple(
            _best_family_representative(group)
            for group in independent_groups
        )
        identity = {"dimension": dimension, "value": value}
        key = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
        candidates.append(
            PatternCandidate(
                pattern_key=f"writing-pattern:v{PATTERN_SCHEMA_VERSION}:{key}",
                dimension=dimension,
                value=value,
                visibility=strictest_visibility(
                    [representative.visibility for representative in representatives]
                ),
                sources=representatives,
            )
        )
    return candidates


def _independent_asset_groups(
    assets: Sequence[KnowledgeAsset],
) -> list[list[KnowledgeAsset]]:
    """Collapse evidence connected by resource, family identity, or exact text hash."""
    items = list(assets)
    parents = list(range(len(items)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    family_owner: dict[str, int] = {}
    hash_owner: dict[str, int] = {}
    resource_owner: dict[str, int] = {}
    for index, asset in enumerate(items):
        previous_resource = resource_owner.setdefault(asset.source.resource_id, index)
        union(index, previous_resource)
        previous_family = family_owner.setdefault(asset.duplicate_family_id, index)
        union(index, previous_family)
        if asset.normalized_hash:
            previous_hash = hash_owner.setdefault(asset.normalized_hash, index)
            union(index, previous_hash)
    grouped: dict[int, list[KnowledgeAsset]] = defaultdict(list)
    for index, asset in enumerate(items):
        grouped[find(index)].append(asset)
    return [
        grouped[root]
        for root in sorted(
            grouped,
            key=lambda key: min(
                (asset.duplicate_family_id, asset.source.resource_id)
                for asset in grouped[key]
            ),
        )
    ]


def pattern_features(content_json: Mapping[str, Any]) -> list[tuple[str, str]]:
    features = extract_writing_features(content_json)
    motifs: set[tuple[str, str]] = set()
    for dimension in _PATTERN_DIMENSIONS:
        value = _normalized_feature_value(features.get(dimension))
        if value:
            motifs.add((dimension, value))
    for value in _string_list(features.get("style_tags")):
        normalized = _normalized_feature_value(value)
        if normalized:
            motifs.add(("style_tag", normalized))
    # knowledge_enrich stores explicit deterministic metadata as plural arrays.  Read
    # those exact fields as well as source content so synthesis never depends on an LLM
    # or silently misses teardown metadata merely because it is pluralized.
    metadata = content_json.get("metadata")
    containers = [content_json]
    if isinstance(metadata, Mapping):
        containers.append(metadata)
    explicit_fields = {
        "hook_type": ("hook_types", "hook_type"),
        "cta_type": ("cta_types", "cta_type"),
        "structure_type": ("structure_tags", "structure_type", "structure"),
        "style_tag": ("style_tags", "style_labels"),
    }
    for container in containers:
        for dimension, keys in explicit_fields.items():
            for key in keys:
                raw = container.get(key)
                values = [raw] if isinstance(raw, str) else _string_list(raw)
                for value in values:
                    normalized = _normalized_feature_value(value)
                    if normalized:
                        motifs.add((dimension, normalized))
    return sorted(motifs)


def strictest_visibility(visibilities: Sequence[str]) -> str:
    if not visibilities:
        raise ValueError("at least one source visibility is required")
    normalized = [normalize_visibility(value) for value in visibilities]
    return min(normalized, key=lambda value: _VISIBILITY_RANK[value])


def normalize_visibility(visibility: str) -> str:
    cleaned = visibility.strip() if isinstance(visibility, str) else ""
    # Unknown visibility fails closed; it must never widen a private source.
    return cleaned if cleaned in _VISIBILITY_RANK else "private"


class PreferenceLearningService:
    """Transaction-aware orchestration over ResourceRepository + preference tables."""

    def __init__(
        self,
        resource_repo: Any,
        preference_repo: Any | None = None,
        account_repo: Any | None = None,
    ) -> None:
        self.resource_repo = resource_repo
        if preference_repo is None:
            from data_foundation.repositories.preference import PreferenceRepository

            preference_repo = PreferenceRepository(resource_repo.conn)
        self.preference_repo = preference_repo
        if account_repo is None:
            account_repo = getattr(resource_repo, "account_repo", None)
        if account_repo is None:
            from data_foundation.repositories.account import AccountRepository

            account_repo = AccountRepository(resource_repo.conn)
        self.account_repo = account_repo

    def record_exact_event(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        event_type: str,
        source_resource_id: str,
        source_resource_version: int,
        source_event_id: str | None = None,
        event_payload: Mapping[str, Any] | None = None,
        base_resource_version: int | None = None,
        rebuild_profile: bool = True,
    ) -> dict[str, Any]:
        source = ExactResourceVersion(source_resource_id, source_resource_version)
        with self.resource_repo.unit_of_work():
            self.preference_repo.acquire_actor_lock(
                tenant_id=tenant_id, actor_open_id=actor_open_id
            )
            snapshot = self._snapshot(
                tenant_id=tenant_id, actor_open_id=actor_open_id, source=source
            )
            previous_snapshot = None
            if normalize_event_type(event_type) == "revision":
                if base_resource_version is None:
                    raise ValueError("base_resource_version is required for revision")
                previous_snapshot = self._snapshot(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    source=ExactResourceVersion(source_resource_id, base_resource_version),
                )
            normalized_event_type = normalize_event_type(event_type)
            enriched_event_payload = dict(event_payload or {})
            if normalized_event_type == "comparison":
                rejected = enriched_event_payload.get("rejected_source")
                if not isinstance(rejected, Mapping):
                    raise ValueError("comparison requires rejected_source")
                rejected_source = ExactResourceVersion(
                    str(rejected.get("resource_id") or ""),
                    rejected.get("resource_version"),
                )
                enriched_event_payload["rejected_features"] = extract_writing_features(
                    self._snapshot(
                        tenant_id=tenant_id,
                        actor_open_id=actor_open_id,
                        source=rejected_source,
                    )
                )
            observation = build_preference_observation(
                event_type=event_type,
                source=source,
                snapshot=snapshot,
                source_event_id=source_event_id,
                event_payload=enriched_event_payload,
                previous_snapshot=previous_snapshot,
            )
            writing_context = context_from_payload(snapshot.get("resource_context"))
            scope_key = writing_context.scope_key
            inserted = self.preference_repo.insert_observation(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                observation=observation,
                scope_key=scope_key,
            )
            profile = None
            if rebuild_profile:
                if inserted:
                    # global 是跨上下文兜底；一旦素材有账号/垂类，同时重建精确范围画像。
                    self._rebuild_profile(
                        tenant_id=tenant_id,
                        actor_open_id=actor_open_id,
                        scope_key=GLOBAL_SCOPE_KEY,
                        writing_context=WritingContext(),
                    )
                    profile = (
                        self._rebuild_profile(
                            tenant_id=tenant_id,
                            actor_open_id=actor_open_id,
                            scope_key=scope_key,
                            writing_context=writing_context,
                        )
                        if scope_key != GLOBAL_SCOPE_KEY
                        else self._profile_result(
                            self.preference_repo.get_profile_state(
                                tenant_id=tenant_id,
                                actor_open_id=actor_open_id,
                                scope_key=GLOBAL_SCOPE_KEY,
                            )
                        )
                    )
                else:
                    # An idempotent replay adds no evidence. Rebuilding anyway walks
                    # the complete observation set and rewrites every learned_from
                    # edge; a scheduled metrics replay therefore grows as O(N^2).
                    # Return the existing pointer without creating graph work.
                    state = self.preference_repo.get_profile_state(
                        tenant_id=tenant_id,
                        actor_open_id=actor_open_id,
                        scope_key=scope_key,
                    )
                    profile = (
                        self._profile_result(state)
                        if state is not None and state.get("profile_resource_id")
                        else self._rebuild_profile(
                            tenant_id=tenant_id,
                            actor_open_id=actor_open_id,
                            scope_key=scope_key,
                            writing_context=writing_context,
                        )
                    )
        return {
            "ok": True,
            "event_key": observation.event_key,
            "inserted": inserted,
            "profile": profile,
        }

    @staticmethod
    def _profile_result(state: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "resource_id": str(state["profile_resource_id"]),
            "resource_version": int(state["profile_resource_version"]),
            "observation_count": int(state["observation_count"]),
            "input_digest": str(state["input_digest"]),
        }

    def rebuild_profile(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        writing_context: WritingContext | None = None,
    ) -> dict[str, Any]:
        context = writing_context or WritingContext()
        with self.resource_repo.unit_of_work():
            self.preference_repo.acquire_actor_lock(
                tenant_id=tenant_id, actor_open_id=actor_open_id
            )
            return self._rebuild_profile(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                scope_key=context.scope_key,
                writing_context=context,
            )

    def _rebuild_profile(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        scope_key: str = GLOBAL_SCOPE_KEY,
        writing_context: WritingContext | None = None,
    ) -> dict[str, Any]:
        context = writing_context or WritingContext()
        observations = self.preference_repo.list_observations(
            tenant_id=tenant_id, actor_open_id=actor_open_id, scope_key=scope_key
        )
        profile = rebuild_preference_profile(actor_open_id, observations)
        profile["writing_context"] = context.payload()
        state = self.preference_repo.get_profile_state(
            tenant_id=tenant_id, actor_open_id=actor_open_id, scope_key=scope_key
        )
        profile_resource_id = (
            str(state["profile_resource_id"])
            if state and state.get("profile_resource_id")
            else str(uuid.uuid5(_PROFILE_NAMESPACE, f"{tenant_id}:{actor_open_id}:{scope_key}"))
        )
        resource = self.resource_repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=profile_resource_id,
            resource_type="writing_preference_profile",
            title=(
                "我的全局写作偏好画像"
                if scope_key == GLOBAL_SCOPE_KEY
                else "我的账号/垂类写作偏好画像"
            ),
            summary=f"基于 {profile['observation_count']} 条确定性行为事实重建",
            content_text=_profile_content_text(profile),
            content_json=profile,
            visibility="private",
            owner_open_id=actor_open_id,
            # Profiles are loaded by writing_profile_states, never by generic retrieval.
            outbox_requests=[],
        )
        profile_version = int(resource.version)
        for source_payload in profile["sources"]:
            self.resource_repo.add_edge(
                tenant_id=tenant_id,
                source_resource_id=str(resource.id),
                source_resource_version=profile_version,
                target_resource_id=source_payload["resource_id"],
                target_resource_version=int(source_payload["resource_version"]),
                edge_type="learned_from",
                weight=1.0,
            )
        self.preference_repo.upsert_profile_state(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            profile_resource_id=str(resource.id),
            profile_resource_version=profile_version,
            input_digest=profile["input_digest"],
            observation_count=profile["observation_count"],
            profile=profile,
            scope_key=scope_key,
        )
        return {
            "resource_id": str(resource.id),
            "resource_version": profile_version,
            "observation_count": profile["observation_count"],
            "input_digest": profile["input_digest"],
        }

    def synthesize_patterns(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        minimum_families: int = MIN_PATTERN_FAMILIES,
        writing_context: WritingContext | None = None,
    ) -> list[dict[str, Any]]:
        saved: list[dict[str, Any]] = []
        with self.resource_repo.unit_of_work():
            self.preference_repo.acquire_actor_lock(
                tenant_id=tenant_id, actor_open_id=actor_open_id
            )
            contexts = [writing_context] if writing_context is not None else [
                WritingContext(),
                *self.preference_repo.list_eligible_contexts(
                    tenant_id=tenant_id, actor_open_id=actor_open_id
                ),
            ]
            unique_contexts = {
                context.scope_key: context
                for context in contexts
                if isinstance(context, WritingContext)
            }
            for scope_key in sorted(unique_contexts):
                saved.extend(
                    self._synthesize_pattern_scope(
                        tenant_id=tenant_id,
                        actor_open_id=actor_open_id,
                        minimum_families=minimum_families,
                        writing_context=unique_contexts[scope_key],
                    )
                )
        return saved

    def _synthesize_pattern_scope(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        minimum_families: int,
        writing_context: WritingContext,
    ) -> list[dict[str, Any]]:
        assets = self.preference_repo.list_eligible_assets(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            writing_context=writing_context,
        )
        candidates = synthesize_pattern_candidates(
            assets, minimum_families=minimum_families
        )
        existing_patterns = {
            str(row["content_json"].get("pattern_key") or ""): row
            for row in self.preference_repo.list_actor_patterns(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                scope_key=writing_context.scope_key,
            )
            if isinstance(row.get("content_json"), dict)
            and str(row["content_json"].get("pattern_key") or "").strip()
        }
        saved: list[dict[str, Any]] = []
        active_pattern_keys: set[str] = set()
        for candidate in candidates:
            active_pattern_keys.add(candidate.pattern_key)
            identity_suffix = (
                candidate.pattern_key
                if writing_context.is_global
                else f"{writing_context.scope_key}:{candidate.pattern_key}"
            )
            resource_id = str(
                uuid.uuid5(
                    _PATTERN_NAMESPACE,
                    f"{tenant_id}:{actor_open_id}:{identity_suffix}",
                )
            )
            source_authority = [
                {
                    **asset.source.payload(),
                    "duplicate_family_id": asset.duplicate_family_id,
                    "visibility": asset.visibility,
                    "quality_score": asset.quality_score,
                    "performance_score": asset.performance_score,
                }
                for asset in candidate.sources
            ]
            content_json = {
                "schema_version": PATTERN_SCHEMA_VERSION,
                "pattern_key": candidate.pattern_key,
                "pattern_features": {
                    "dimension": candidate.dimension,
                    "value": candidate.value,
                },
                "synthesis_threshold": minimum_families,
                "source_family_ids": list(candidate.source_family_ids),
                "source_authority": source_authority,
                "writing_context": writing_context.payload(),
            }
            resource = self.resource_repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=resource_id,
                resource_type="writing_pattern",
                title=f"写作模式 · {candidate.dimension} · {candidate.value}",
                summary=f"由 {len(candidate.sources)} 个独立素材家族确定性归纳",
                content_text=_pattern_content_text(candidate),
                content_json=content_json,
                visibility=candidate.visibility,
                owner_open_id=actor_open_id,
                outbox_requests=default_write_requests(),
            )
            pattern_version = int(resource.version)
            connection = getattr(self.resource_repo, "conn", None)
            if not writing_context.is_global and callable(
                getattr(connection, "execute", None)
            ):
                from data_foundation.repositories.account import AccountRepository

                AccountRepository(connection).attach_resource_context(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    resource_id=str(resource.id),
                    resource_version=pattern_version,
                    context=writing_context,
                    source="source_metadata",
                )
            for asset in candidate.sources:
                self.resource_repo.add_edge(
                    tenant_id=tenant_id,
                    source_resource_id=str(resource.id),
                    source_resource_version=pattern_version,
                    target_resource_id=asset.source.resource_id,
                    target_resource_version=asset.source.resource_version,
                    edge_type="synthesized_from",
                    weight=1.0,
                )
            saved.append(
                {
                    "resource_id": str(resource.id),
                    "resource_version": pattern_version,
                    "pattern_key": candidate.pattern_key,
                    "visibility": candidate.visibility,
                    "source_family_count": len(candidate.sources),
                    "status": "active",
                    "writing_context": writing_context.payload(),
                }
            )
        for pattern_key, previous in existing_patterns.items():
            if pattern_key in active_pattern_keys or previous.get("status") != "active":
                continue
            retired_content = {
                **dict(previous.get("content_json") or {}),
                "retired_reason": "CURRENT_READABLE_EVIDENCE_NO_LONGER_MEETS_THRESHOLD",
                "writing_context": writing_context.payload(),
            }
            retired = self.resource_repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=str(previous["resource_id"]),
                resource_type="writing_pattern",
                title=str(previous.get("title") or "写作模式"),
                summary=str(previous.get("summary") or "证据已失效的写作模式"),
                content_text=str(previous.get("content_text") or ""),
                content_json=retired_content,
                status="inactive",
                visibility=normalize_visibility(str(previous.get("visibility") or "private")),
                owner_open_id=actor_open_id,
                outbox_requests=default_write_requests(),
            )
            saved.append(
                {
                    "resource_id": str(retired.id),
                    "resource_version": int(retired.version),
                    "pattern_key": pattern_key,
                    "visibility": normalize_visibility(
                        str(previous.get("visibility") or "private")
                    ),
                    "source_family_count": 0,
                    "status": "retired",
                    "writing_context": writing_context.payload(),
                }
            )
        return saved

    def mark_synthesis_completed(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        requested_revision: int,
    ) -> bool:
        return self.preference_repo.mark_synthesis_completed(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            requested_revision=requested_revision,
        )

    def get_profile(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        writing_context: WritingContext | None = None,
    ) -> dict[str, Any]:
        context = writing_context or WritingContext()
        if context.account_id is not None:
            self.account_repo.assert_owned_context(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                context=context,
            )
        state = self.preference_repo.get_profile_state(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            scope_key=context.scope_key,
        )
        resolved_scope = context.scope_key
        if state is None and context.scope_key != GLOBAL_SCOPE_KEY:
            state = self.preference_repo.get_profile_state(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                scope_key=GLOBAL_SCOPE_KEY,
            )
            resolved_scope = GLOBAL_SCOPE_KEY
        if state is None:
            return {
                "ok": True,
                "profile": None,
                "requested_scope": context.scope_key,
                "resolved_scope": None,
            }
        resource = self.resource_repo.get_resource_version(
            tenant_id,
            actor_open_id,
            str(state["profile_resource_id"]),
            int(state["profile_resource_version"]),
        )
        if resource is None or resource.type != "writing_preference_profile":
            return {"ok": True, "profile": None}
        return {
            "ok": True,
            "profile": {
                "resource_id": str(resource.id),
                "resource_version": int(resource.version),
                "observation_count": int(state["observation_count"]),
                "content": dict(resource.content_json or {}),
                "requested_scope": context.scope_key,
                "resolved_scope": resolved_scope,
            },
        }

    def _snapshot(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        source: ExactResourceVersion,
    ) -> dict[str, Any]:
        resource = self.resource_repo.get_resource_version(
            tenant_id,
            actor_open_id,
            source.resource_id,
            source.resource_version,
        )
        if resource is None:
            raise ValueError("exact source resource version is not readable")
        snapshot = dict(resource.content_json or {})
        snapshot.setdefault("title", resource.title)
        snapshot.setdefault("content_text", resource.content_text or "")
        # resource_contexts 是精确版本上下文的唯一真源。即使 content_json 中残留了
        # 生成时的旧字段，排期绑定后的生命周期事实也必须进入权威账号范围。
        context = self.account_repo.get_resource_context(
            tenant_id=tenant_id,
            resource_id=source.resource_id,
            resource_version=source.resource_version,
            actor_open_id=actor_open_id,
        )
        snapshot["resource_context"] = context.payload()
        return snapshot


def _revision_signal(*, before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    changed_fields = [
        field
        for field in (
            "title_length",
            "body_length",
            "paragraph_count",
            "tags",
            "hook_type",
            "cta_type",
            "structure_type",
        )
        if before.get(field) != after.get(field)
    ]
    return {
        "changed_fields": changed_fields,
        "title_length_delta": int(after["title_length"]) - int(before["title_length"]),
        "body_length_delta": int(after["body_length"]) - int(before["body_length"]),
        "paragraph_count_delta": int(after["paragraph_count"])
        - int(before["paragraph_count"]),
        "tags_added": sorted(set(after["tags"]) - set(before["tags"])),
        "tags_removed": sorted(set(before["tags"]) - set(after["tags"])),
    }


def _metric_signal(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_metrics = payload.get("metrics")
    metrics: dict[str, float | int] = {}
    if isinstance(raw_metrics, Mapping):
        for key, value in sorted(raw_metrics.items()):
            if not isinstance(key, str) or isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number) and number >= 0:
                metrics[key] = int(number) if number.is_integer() else number
    score = payload.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        score = None
    exact_sources: list[dict[str, Any]] = []
    try:
        metric_source = ExactResourceVersion(
            str(payload.get("metric_resource_id") or ""),
            payload.get("metric_resource_version"),
        )
    except ValueError:
        pass
    else:
        exact_sources.append(metric_source.payload())
    normalized = payload.get("normalized_performance")
    normalized = dict(normalized) if isinstance(normalized, Mapping) else {}
    if not normalized:
        rebuilt = normalize_performance(
            metrics,
            published_at=payload.get("published_at"),
        )
        normalized = rebuilt.payload()
        score = rebuilt.score
    confidence = normalized.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
        confidence = 0.0
    return {
        "metrics": metrics,
        "score": score,
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "learning_eligible": normalized.get("learning_eligible") is True,
        "exact_sources": exact_sources,
    }


def _observation_weight(observation: PreferenceObservation) -> float:
    base = _EVENT_WEIGHTS[observation.event_type]
    if observation.event_type != "metric":
        return base
    signal = dict(observation.payload.get("signal") or {})
    factor = _metric_signal_factor(signal)
    return base * factor


def _metric_signal_factor(signal: Mapping[str, Any]) -> float:
    if signal.get("learning_eligible") is not True:
        return 0.0
    confidence = signal.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
    ):
        return 0.0
    return _metric_outcome_factor(signal.get("score")) * max(
        0.0, min(float(confidence), 1.0)
    )


def _metric_lifecycle_factor(signal: Mapping[str, Any]) -> float:
    # 缺曝光/观察窗不足是“证据未知”，不能把已经采纳、发布的正向事实归零。
    if signal.get("learning_eligible") is not True:
        return 1.0
    return _metric_signal_factor(signal)


def _metric_outcome_factor(score: Any) -> float:
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or score < MIN_PATTERN_PERFORMANCE
    ):
        return 0.0
    return float(score) / (float(score) + METRIC_SCORE_PIVOT)


def _feedback_signal(
    payload: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    feedback = _text(payload.get("feedback")) or _text(snapshot.get("feedback"))
    traits: set[str] = set()
    trait_tokens = {
        "更简洁": ("短一点", "精简", "简洁", "太长", "啰嗦"),
        "更具体": ("具体", "细节", "案例", "例子", "数据"),
        "降低AI腔": ("ai味", "ai 味", "ai 腔", "机器味", "自然一点", "不像人话"),
        "增强个人感": ("个人", "经历", "我的", "人设", "像我"),
        "调整标题": ("标题", "题目"),
        "调整语气": ("语气", "口语", "正式", "轻松", "犀利", "温柔"),
        "减少Emoji": ("少点emoji", "少点 emoji", "不要emoji", "不要 emoji"),
        "增加Emoji": ("加点emoji", "加点 emoji", "多点emoji", "多点 emoji"),
    }
    lowered = feedback.lower()
    for trait, tokens in trait_tokens.items():
        if any(token in lowered for token in tokens):
            traits.add(trait)
    return {
        "feedback": feedback,
        "feedback_type": _text(payload.get("feedback_type")),
        "traits": sorted(traits),
    }


def _pairwise_bias_weight(signal: Mapping[str, Any]) -> float:
    chosen = signal.get("chosen_ordinal")
    rejected = signal.get("rejected_ordinal")
    if not isinstance(chosen, int) or not isinstance(rejected, int):
        return 1.0
    # 选中后位版本说明偏好克服了首位展示优势；首位胜出则适度降权，避免把位置偏差
    # 误学成强烈内容厌恶。原始 ordinal 同时永久保存，可离线重估 propensity。
    return 1.15 if chosen > rejected else 0.7 if chosen < rejected else 1.0


def _weighted_range(values: list[tuple[float, float]]) -> dict[str, float | int]:
    total_weight = sum(weight for _, weight in values)
    mean = sum(value * weight for value, weight in values) / total_weight
    raw_values = [value for value, _ in values]
    return {
        "preferred": round(mean, 2),
        "observed_min": int(min(raw_values)),
        "observed_max": int(max(raw_values)),
    }


def _ranked_values(scores: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"value": value, "score": round(float(score), 3)}
        for value, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _best_family_representative(assets: Sequence[KnowledgeAsset]) -> KnowledgeAsset:
    return sorted(
        assets,
        key=lambda asset: (
            asset.performance_score is None,
            -(asset.performance_score or 0.0),
            -asset.quality_score,
            asset.source.resource_id,
            -asset.source.resource_version,
        ),
    )[0]


def _profile_content_text(profile: Mapping[str, Any]) -> str:
    lines = [
        "写作偏好画像",
        f"观察数: {profile['observation_count']}",
        f"精确来源数: {profile['source_count']}",
    ]
    for dimension, values in dict(profile.get("preferences") or {}).items():
        if values:
            lines.append(f"{dimension}: " + "、".join(item["value"] for item in values[:5]))
    return "\n".join(lines)


def _pattern_content_text(candidate: PatternCandidate) -> str:
    return "\n".join(
        [
            "写作模式",
            f"维度: {candidate.dimension}",
            f"模式: {candidate.value}",
            f"独立素材家族: {len(candidate.sources)}",
        ]
    )


def _first_text(content: Mapping[str, Any], *keys: str) -> str:
    metadata = content.get("metadata")
    candidates: list[Mapping[str, Any]] = [content]
    if isinstance(metadata, Mapping):
        candidates.append(metadata)
    for candidate in candidates:
        for key in keys:
            value = _text(candidate.get(key))
            if value:
                return value
    return ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [_text(item) for item in value if _text(item)]


def _normalized_feature_value(value: Any) -> str:
    text = re.sub(r"\s+", " ", _text(value)).strip().lower()
    return text[:120]


def _infer_hook_type(title: str) -> str:
    if not title:
        return ""
    if re.search(r"\d", title):
        return "数字清单"
    if any(token in title for token in ("别", "不要", "千万", "避坑", "踩坑")):
        return "避坑警示"
    if any(token in title for token in ("为什么", "怎么", "如何", "?", "？")):
        return "问题悬念"
    if any(token in title for token in ("没想到", "居然", "原来", "反而")):
        return "反常识"
    return ""


def _infer_cta_type(body: str) -> str:
    tail = body[-160:]
    if any(token in tail for token in ("评论区", "留言", "你会怎么")):
        return "评论互动"
    if "收藏" in tail:
        return "收藏"
    if any(token in tail for token in ("关注", "下篇")):
        return "关注追更"
    return ""


def _infer_structure_type(paragraphs: Sequence[str]) -> str:
    count = len(paragraphs)
    if count == 0:
        return ""
    if count <= 3:
        return "短段落"
    if count <= 7:
        return "中段落"
    return "多段清单"


__all__ = [
    "ExactResourceVersion",
    "KnowledgeAsset",
    "MIN_PATTERN_FAMILIES",
    "MIN_PATTERN_PERFORMANCE",
    "MIN_PATTERN_QUALITY",
    "PatternCandidate",
    "PreferenceLearningService",
    "PreferenceObservation",
    "build_preference_observation",
    "canonical_json",
    "extract_writing_features",
    "normalize_event_type",
    "normalize_visibility",
    "pattern_features",
    "preference_event_key",
    "rebuild_preference_profile",
    "strictest_visibility",
    "synthesize_pattern_candidates",
]
