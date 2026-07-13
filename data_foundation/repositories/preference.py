from __future__ import annotations

import json
from typing import Any

from psycopg.rows import dict_row

from data_foundation.preference_learning import (
    ExactResourceVersion,
    KnowledgeAsset,
    PreferenceObservation,
)
from data_foundation.repositories.base import BaseRepository


class PreferenceRepository(BaseRepository):
    """Actor-scoped observations, profile pointer state, and qualified pattern inputs."""

    def acquire_actor_lock(self, *, tenant_id: str, actor_open_id: str) -> None:
        """Serialize one actor's observation/profile/pattern write transaction."""
        lock_key = f"writing-preference:{tenant_id}:{actor_open_id}"
        with self.connection_context() as connection:
            connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (lock_key,),
            )

    def insert_observation(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        observation: PreferenceObservation,
    ) -> bool:
        metadata = {"source_event_id": observation.source_event_id}
        with self.connection_context() as connection:
            with connection.transaction():
                row = connection.execute(
                    """
                    insert into preference_observations (
                      tenant_id, owner_open_id, resource_id, resource_version,
                      observation_type, signal, weight, idempotency_key, metadata
                    ) values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                    on conflict (tenant_id, owner_open_id, idempotency_key) do nothing
                    returning id
                    """,
                    (
                        tenant_id,
                        actor_open_id,
                        observation.source.resource_id,
                        observation.source.resource_version,
                        observation.event_type,
                        json.dumps(observation.payload, ensure_ascii=False, sort_keys=True),
                        1.0,
                        observation.event_key,
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    ),
                ).fetchone()
                return row is not None

    def list_observations(
        self, *, tenant_id: str, actor_open_id: str
    ) -> list[PreferenceObservation]:
        with self.connection_context() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    select resource_id::text, resource_version, observation_type,
                           signal, idempotency_key, metadata
                    from preference_observations
                    where tenant_id = %s and owner_open_id = %s
                    order by idempotency_key
                    """,
                    (tenant_id, actor_open_id),
                ).fetchall()
        observations: list[PreferenceObservation] = []
        for row in rows:
            metadata = dict(row["metadata"] or {})
            observations.append(
                PreferenceObservation(
                    event_key=row["idempotency_key"],
                    event_type=row["observation_type"],
                    source=ExactResourceVersion(
                        str(row["resource_id"]), int(row["resource_version"])
                    ),
                    source_event_id=metadata.get("source_event_id"),
                    payload=dict(row["signal"] or {}),
                )
            )
        return observations

    def get_profile_state(
        self, *, tenant_id: str, actor_open_id: str
    ) -> dict[str, Any] | None:
        with self.connection_context() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    """
                    select tenant_id, owner_open_id, profile_resource_id::text,
                           profile_resource_version, input_digest, observation_count,
                           profile, evidence_count, revision, rebuilt_through,
                           created_at, updated_at
                    from writing_profile_states
                    where tenant_id = %s and owner_open_id = %s
                    """,
                    (tenant_id, actor_open_id),
                ).fetchone()
                return None if row is None else dict(row)

    def upsert_profile_state(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        profile_resource_id: str,
        profile_resource_version: int,
        input_digest: str,
        observation_count: int,
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile_payload = dict(profile or {})
        with self.connection_context() as connection:
            with connection.transaction():
                row = connection.execute(
                    """
                    insert into writing_profile_states (
                      tenant_id, owner_open_id, profile_resource_id, profile_resource_version,
                      input_digest, observation_count, profile, evidence_count,
                      revision, rebuilt_through
                    ) values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, 1, now())
                    on conflict (tenant_id, owner_open_id) do update
                    set profile_resource_id = excluded.profile_resource_id,
                        profile_resource_version = excluded.profile_resource_version,
                        input_digest = excluded.input_digest,
                        observation_count = excluded.observation_count,
                        profile = excluded.profile,
                        evidence_count = excluded.evidence_count,
                        revision = case
                          when writing_profile_states.input_digest = excluded.input_digest
                            then writing_profile_states.revision
                          else writing_profile_states.revision + 1
                        end,
                        rebuilt_through = case
                          when writing_profile_states.input_digest = excluded.input_digest
                            then writing_profile_states.rebuilt_through
                          else now()
                        end,
                        updated_at = case
                          when writing_profile_states.input_digest = excluded.input_digest
                            then writing_profile_states.updated_at
                          else now()
                        end
                    returning *
                    """,
                    (
                        tenant_id,
                        actor_open_id,
                        profile_resource_id,
                        profile_resource_version,
                        input_digest,
                        observation_count,
                        json.dumps(profile_payload, ensure_ascii=False, sort_keys=True),
                        observation_count,
                    ),
                ).fetchone()
                return dict(row)

    def list_eligible_assets(
        self, *, tenant_id: str, actor_open_id: str
    ) -> list[KnowledgeAsset]:
        """Return exact qualified inputs, excluding other users' private assets."""
        with self.connection_context() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    select q.resource_id::text, q.resource_version,
                           q.duplicate_family_id::text, live.visibility,
                           q.content_json, q.metadata, q.quality_score,
                           q.normalized_hash,
                           coalesce(enrichment.payload, '{}'::jsonb) as enrichment
                    from current_knowledge_targets q
                    join resources live
                      on live.tenant_id = q.tenant_id
                     and live.id = q.resource_id
                     and live.status = 'active'
                    left join lateral (
                      select ke.payload
                      from knowledge_enrichments ke
                      where ke.tenant_id = q.tenant_id
                        and ke.resource_id = q.resource_id
                        and ke.resource_version = q.resource_version
                        and ke.enrichment_type = 'deterministic_metadata'
                      order by ke.created_at desc, ke.id desc
                      limit 1
                    ) enrichment on true
                    where q.tenant_id = %s
                      and q.eligible_for_synthesis is true
                      and q.duplicate_family_id is not null
                      and (
                        live.visibility = 'team'
                        or live.owner_open_id = %s
                        or exists (
                          select 1
                          from resource_permissions rp
                          where rp.tenant_id = live.tenant_id
                            and rp.resource_id = live.id
                            and rp.subject_type = 'user'
                            and rp.subject_id = %s
                            and rp.permission in ('read', 'write', 'admin')
                        )
                      )
                    order by q.duplicate_family_id, q.resource_id, q.resource_version
                    """,
                    (tenant_id, actor_open_id, actor_open_id),
                ).fetchall()
        assets: list[KnowledgeAsset] = []
        for row in rows:
            content = dict(row["content_json"] or {})
            metadata = {
                **dict(row["metadata"] or {}),
                **dict(row["enrichment"] or {}),
            }
            if metadata:
                content["metadata"] = metadata
            assets.append(
                KnowledgeAsset(
                    source=ExactResourceVersion(
                        str(row["resource_id"]), int(row["resource_version"])
                    ),
                    duplicate_family_id=str(row["duplicate_family_id"]),
                    visibility=row["visibility"],
                    content_json=content,
                    quality_score=float(row["quality_score"] or 0.0),
                    normalized_hash=row["normalized_hash"],
                )
            )
        return assets

    def list_actor_patterns(
        self, *, tenant_id: str, actor_open_id: str
    ) -> list[dict[str, Any]]:
        """Return every latest actor-owned pattern, including inactive ones."""
        with self.connection_context() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    select r.id::text as resource_id, r.status, r.title, r.summary,
                           r.visibility, r.owner_open_id, rv.version as resource_version,
                           rv.content_text, rv.content_json
                    from resources r
                    join lateral (
                      select exact.version, exact.content_text, exact.content_json
                      from resource_versions exact
                      where exact.tenant_id = r.tenant_id
                        and exact.resource_id = r.id
                      order by exact.version desc
                      limit 1
                    ) rv on true
                    where r.tenant_id = %s
                      and r.owner_open_id = %s
                      and r.type = 'writing_pattern'
                    order by r.id
                    """,
                    (tenant_id, actor_open_id),
                ).fetchall()
        return [dict(row) for row in rows]

    def mark_synthesis_completed(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        requested_revision: int,
    ) -> bool:
        if requested_revision <= 0:
            raise ValueError("requested_revision must be positive")
        with self.connection_context() as connection:
            with connection.transaction():
                state = connection.execute(
                    """
                    select requested_revision, completed_revision
                    from preference_synthesis_states
                    where tenant_id = %s and owner_open_id = %s
                    for update
                    """,
                    (tenant_id, actor_open_id),
                ).fetchone()
                if state is None or int(state["requested_revision"]) != requested_revision:
                    return False
                if int(state["completed_revision"]) == requested_revision:
                    # The completion transaction may commit immediately before the
                    # outbox worker loses its lease or crashes.  Replaying that exact
                    # revision is success, not a stale-revision failure.
                    return True
                row = connection.execute(
                    """
                    update preference_synthesis_states
                    set completed_revision = %s, updated_at = now()
                    where tenant_id = %s and owner_open_id = %s
                      and requested_revision = %s
                      and completed_revision < %s
                    returning completed_revision
                    """,
                    (
                        requested_revision,
                        tenant_id,
                        actor_open_id,
                        requested_revision,
                        requested_revision,
                    ),
                ).fetchone()
        return row is not None


__all__ = ["PreferenceRepository"]
