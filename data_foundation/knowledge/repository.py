from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.knowledge.models import (
    KnowledgeDecision,
    KnowledgeEnrichResult,
    KnowledgeSnapshot,
)
from data_foundation.knowledge.locking import acquire_classification_lock
from data_foundation.knowledge.normalizer import normalize_knowledge_text, normalized_hash
from data_foundation.preference_outbox import enqueue_preference_synthesis


PIPELINE_VERSION = "knowledge-enrich-v1"
ANCHOR_NAMESPACE = uuid.UUID("8b45980a-c51b-4ffd-9169-7db5b2848bc6")
SESSION_SNAPSHOT_KINDS = frozenset(
    {
        "workflow_state",
        "diagnosis",
        "positioning",
        "decision",
        "learning_chapter",
        "content_system",
        "stage_report",
        "migration_audit",
    }
)


class KnowledgeRepository:
    def __init__(self, conn: Connection):
        self.conn = conn

    @contextmanager
    def classification_scope(
        self,
        *,
        tenant_id: str,
        resource_id: str,
    ) -> Iterator[None]:
        """Hold the exact-resource lock from snapshot read through state persistence."""
        with self.conn.transaction():
            acquire_classification_lock(
                self.conn,
                tenant_id=tenant_id,
                resource_id=resource_id,
            )
            yield

    def load_snapshot(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        resource_version: int,
    ) -> KnowledgeSnapshot | None:
        if resource_version <= 0:
            raise ValueError("resource_version must be a positive integer")
        with self.conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                select r.tenant_id, r.id::text as resource_id, rv.version as resource_version,
                       r.type as resource_type, r.status, r.visibility, r.owner_open_id,
                       coalesce(nullif(rv.content_json->>'title', ''), r.title) as title,
                       coalesce(rv.content_text, '') as content_text, rv.content_json,
                       gcs.lifecycle_status, gcs.state_version as lifecycle_state_version,
                       gcs.knowledge_target_version,
                       coalesce(kas.metadata->'confirmation', '{}'::jsonb) as confirmation_metadata,
                       coalesce((
                         select count(distinct target_state.duplicate_family_id)
                         from resource_edges edge
                         join knowledge_asset_states target_state
                           on target_state.tenant_id = edge.tenant_id
                          and target_state.resource_id = edge.target_resource_id
                          and target_state.resource_version = edge.target_resource_version
                         where edge.tenant_id = r.tenant_id
                           and edge.source_resource_id = r.id
                           and edge.source_resource_version = rv.version
                           and edge.edge_type = 'synthesized_from'
                           and target_state.eligibility = 'qualified'
                           and target_state.eligible_for_synthesis is true
                           and target_state.duplicate_family_id is not null
                       ), 0)::int as synthesis_family_count,
                       coalesce((
                          select count(*)
                          from resource_edges edge
                          join base_current_knowledge_targets target
                            on target.tenant_id = edge.tenant_id
                           and target.resource_id = edge.target_resource_id
                           and target.resource_version = edge.target_resource_version
                           and target.asset_kind <> 'teardown'
                          where edge.tenant_id = r.tenant_id
                           and edge.source_resource_id = r.id
                           and edge.source_resource_version = rv.version
                           and edge.edge_type = 'teardown_of'
                       ), 0)::int as teardown_source_count,
                       coalesce((
                         select array_agg(distinct rm.system order by rm.system)
                         from resource_mappings rm
                         where rm.tenant_id = r.tenant_id and rm.resource_id = r.id
                       ), array[]::text[]) as mapping_systems
                from resources r
                join resource_versions rv
                  on rv.tenant_id = r.tenant_id and rv.resource_id = r.id
                left join generated_copy_states gcs
                  on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
                left join knowledge_asset_states kas
                  on kas.tenant_id = rv.tenant_id
                 and kas.resource_id = rv.resource_id
                 and kas.resource_version = rv.version
                where r.tenant_id = %s and r.id = %s and rv.version = %s
                """,
                (tenant_id, resource_id, resource_version),
            ).fetchone()
        if row is None:
            return None
        return KnowledgeSnapshot(
            tenant_id=row["tenant_id"],
            resource_id=row["resource_id"],
            resource_version=int(row["resource_version"]),
            resource_type=row["resource_type"],
            status=row["status"],
            visibility=row["visibility"],
            owner_open_id=row["owner_open_id"],
            title=row["title"],
            content_text=row["content_text"],
            content_json=dict(row["content_json"] or {}),
            lifecycle_status=row["lifecycle_status"],
            lifecycle_state_version=(
                None
                if row["lifecycle_state_version"] is None
                else int(row["lifecycle_state_version"])
            ),
            knowledge_target_version=row["knowledge_target_version"],
            mapping_systems=tuple(row["mapping_systems"] or ()),
            confirmation_metadata=dict(row["confirmation_metadata"] or {}),
            synthesis_family_count=int(row["synthesis_family_count"] or 0),
            teardown_source_count=int(row["teardown_source_count"] or 0),
        )

    def persist_enrichment(
        self,
        *,
        snapshot: KnowledgeSnapshot,
        decision: KnowledgeDecision,
        normalized_text: str,
        enrichment_metadata: dict[str, Any],
    ) -> KnowledgeEnrichResult:
        digest = normalized_hash(normalized_text)
        with self.conn.transaction():
            with self.conn.cursor(row_factory=dict_row) as cur:
                # Family matching and anchor creation must serialize within a tenant.
                # The service already owns the exact-resource classification lock; this
                # consistently second lock protects cross-resource family assignment.
                cur.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"knowledge-family:{snapshot.tenant_id}",),
                )
                family_id: str | None = None
                duplicate_kind: str | None = None
                variant_id: str | None = None
                variant_version: int | None = None
                duplicate_similarity: float | None = None
                if decision.eligibility == "qualified":
                    (
                        family_id,
                        duplicate_kind,
                        variant_id,
                        variant_version,
                        duplicate_similarity,
                    ) = self._resolve_family(
                        cur,
                        snapshot=snapshot,
                        normalized_text=normalized_text,
                        digest=digest,
                    )

                qualified_at_sql = "now()" if decision.eligibility == "qualified" else "null"
                row = cur.execute(
                    f"""
                    insert into knowledge_asset_states (
                      tenant_id, resource_id, resource_version, eligibility,
                      eligible_for_synthesis, asset_kind, source_kind, source_authority,
                      quality_score, normalized_text, normalized_hash,
                      duplicate_family_id, duplicate_kind,
                      variant_of_resource_id, variant_of_resource_version,
                      visibility, owner_open_id, metadata, qualified_at, indexed_at,
                      search_reconcile_generation
                    ) values (
                      %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                      {qualified_at_sql}, null, 1
                    )
                    on conflict (tenant_id, resource_id, resource_version) do update set
                      eligibility = excluded.eligibility,
                      eligible_for_synthesis = excluded.eligible_for_synthesis,
                      asset_kind = excluded.asset_kind,
                      source_kind = excluded.source_kind,
                      source_authority = excluded.source_authority,
                      quality_score = excluded.quality_score,
                      normalized_text = excluded.normalized_text,
                      normalized_hash = excluded.normalized_hash,
                      duplicate_family_id = excluded.duplicate_family_id,
                      duplicate_kind = excluded.duplicate_kind,
                      variant_of_resource_id = excluded.variant_of_resource_id,
                      variant_of_resource_version = excluded.variant_of_resource_version,
                      visibility = excluded.visibility,
                      owner_open_id = excluded.owner_open_id,
                      metadata = knowledge_asset_states.metadata || excluded.metadata,
                      qualified_at = excluded.qualified_at,
                      indexed_at = null,
                      search_reconcile_generation =
                        knowledge_asset_states.search_reconcile_generation + 1,
                      updated_at = now()
                    returning eligibility, search_reconcile_generation
                    """,
                    (
                        snapshot.tenant_id,
                        snapshot.resource_id,
                        snapshot.resource_version,
                        decision.eligibility,
                        decision.eligible_for_synthesis,
                        decision.asset_kind,
                        decision.source_kind,
                        json.dumps(decision.source_authority, sort_keys=True, ensure_ascii=False),
                        decision.quality_score,
                        normalized_text,
                        digest,
                        family_id,
                        duplicate_kind,
                        variant_id,
                        variant_version,
                        snapshot.visibility,
                        snapshot.owner_open_id,
                        json.dumps(
                            {
                                "policy_reason": decision.reason_code,
                                "duplicate_similarity": duplicate_similarity,
                            },
                            sort_keys=True,
                            ensure_ascii=False,
                        ),
                    ),
                ).fetchone()

                enrichment_payload = {
                    **enrichment_metadata,
                    "asset_kind": decision.asset_kind,
                    "source_kind": decision.source_kind,
                    "source_authority": decision.source_authority,
                    "quality_score": decision.quality_score,
                    "policy_reason": decision.reason_code,
                    "duplicate_kind": duplicate_kind,
                    "duplicate_family_id": family_id,
                    "duplicate_similarity": duplicate_similarity,
                }
                payload_json = json.dumps(enrichment_payload, sort_keys=True, ensure_ascii=False)
                enrichment_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
                cur.execute(
                    """
                    insert into knowledge_enrichments (
                      tenant_id, resource_id, resource_version, enrichment_type,
                      pipeline_version, payload, content_hash, created_by
                    ) values (%s, %s, %s, 'deterministic_metadata', %s, %s::jsonb, %s, %s)
                    on conflict (
                      tenant_id, resource_id, resource_version,
                      enrichment_type, pipeline_version, content_hash
                    ) do nothing
                    """,
                    (
                        snapshot.tenant_id,
                        snapshot.resource_id,
                        snapshot.resource_version,
                        PIPELINE_VERSION,
                        payload_json,
                        enrichment_hash,
                        "knowledge_enrich",
                    ),
                )

                self._ensure_family_edge(
                    cur,
                    snapshot=snapshot,
                    family_id=family_id,
                    duplicate_kind=duplicate_kind,
                    canonical_resource_id=variant_id,
                    canonical_resource_version=variant_version,
                    similarity=duplicate_similarity,
                )
                anchor_id, anchor_version, edge_created = self._ensure_no_island(cur, snapshot=snapshot)
                topics: list[str] = []
                self._enqueue_exact(
                    cur,
                    tenant_id=snapshot.tenant_id,
                    resource_id=snapshot.resource_id,
                    resource_version=snapshot.resource_version,
                    topic="graph_ingest",
                    suffix=("knowledge-graph",),
                )
                topics.append("graph_ingest")
                had_synthesis_input = cur.execute(
                    """
                    select 1 from knowledge_asset_states
                    where tenant_id = %s and resource_id = %s
                      and eligible_for_synthesis is true
                    limit 1
                    """,
                    (snapshot.tenant_id, snapshot.resource_id),
                ).fetchone() is not None
                if (
                    snapshot.resource_type != "writing_pattern"
                    and (decision.eligible_for_synthesis or had_synthesis_input)
                ):
                    trigger_key = ":".join(
                        (
                            "knowledge",
                            PIPELINE_VERSION,
                            snapshot.resource_id,
                            str(snapshot.resource_version),
                            decision.eligibility,
                            digest,
                            snapshot.status,
                            snapshot.visibility,
                            str(snapshot.lifecycle_state_version or 0),
                            decision.source_kind,
                            f"{decision.quality_score:.4f}",
                        )
                    )
                    enqueued = False
                    for synthesis_actor in self._synthesis_actor_ids(cur, snapshot=snapshot):
                        revision = enqueue_preference_synthesis(
                            cur,
                            tenant_id=snapshot.tenant_id,
                            actor_open_id=synthesis_actor,
                            trigger_key=trigger_key,
                            trigger_payload={
                                "kind": "knowledge_state",
                                "resource_id": snapshot.resource_id,
                                "resource_version": snapshot.resource_version,
                                "eligibility": decision.eligibility,
                            },
                        )
                        enqueued = enqueued or revision is not None
                    if enqueued:
                        topics.append("preference_synthesize")
                if edge_created:
                    self._enqueue_exact(
                        cur,
                        tenant_id=snapshot.tenant_id,
                        resource_id=anchor_id,
                        resource_version=anchor_version,
                        topic="graph_ingest",
                        suffix=("knowledge-anchor",),
                    )

                current = False
                if decision.eligibility == "qualified":
                    current = cur.execute(
                        """
                        select 1 from current_knowledge_targets
                        where tenant_id = %s and resource_id = %s and resource_version = %s
                        """,
                        (snapshot.tenant_id, snapshot.resource_id, snapshot.resource_version),
                    ).fetchone() is not None
                # Every exact classification reconciles the external keyword index.
                # The processor upserts only a current qualified target, keeps a newer
                # current version, and deletes a rejected/resource-less document.  A
                # rejected legacy asset therefore cannot survive in Meili forever.
                self._enqueue_exact(
                    cur,
                    tenant_id=snapshot.tenant_id,
                    resource_id=snapshot.resource_id,
                    resource_version=snapshot.resource_version,
                    topic="meili_index",
                    suffix=(
                        "knowledge-search-reconcile-v2",
                        str(int(row["search_reconcile_generation"])),
                    ),
                    requeue_terminal=True,
                    payload_extra={
                        "reconcile_generation": int(row["search_reconcile_generation"]),
                    },
                )
                topics.append("meili_index")
                self._enqueue_teardown_dependents(
                    cur,
                    snapshot=snapshot,
                    decision=decision,
                    digest=digest,
                )
                if current:
                    embedding_rows = cur.execute(
                        """
                        select id::text as id, chunker_version
                        from embedding_indexes
                        where tenant_id = %s and status in ('active', 'building')
                        order by created_at, id
                        """,
                        (snapshot.tenant_id,),
                    ).fetchall()
                    for embedding_index in embedding_rows:
                        self._enqueue_embedding(
                            cur,
                            tenant_id=snapshot.tenant_id,
                            resource_id=snapshot.resource_id,
                            resource_version=snapshot.resource_version,
                            embedding_index_id=embedding_index["id"],
                            chunker_version=embedding_index["chunker_version"],
                        )
                        topics.append("embedding_generate")
                    cur.execute(
                        """
                        update knowledge_asset_states set indexed_at = now(), updated_at = now()
                        where tenant_id = %s and resource_id = %s and resource_version = %s
                        """,
                        (snapshot.tenant_id, snapshot.resource_id, snapshot.resource_version),
                    )

        status = "qualified" if row["eligibility"] == "qualified" else "rejected"
        return KnowledgeEnrichResult(
            status=status,
            resource_id=snapshot.resource_id,
            resource_version=snapshot.resource_version,
            family_id=family_id,
            duplicate_kind=duplicate_kind,
            downstream_topics=tuple(dict.fromkeys(topics)),
        )

    def confirm_exact_version(
        self,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        asset_kind: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Confirm an exact strategy/session version, then re-enter knowledge_enrich."""
        if resource_version <= 0:
            raise ValueError("resource_version must be a positive integer")
        if asset_kind != "strategy_fact":
            raise ValueError("only strategy_fact can be manually confirmed")
        with self.conn.transaction():
            acquire_classification_lock(
                self.conn,
                tenant_id=tenant_id,
                resource_id=resource_id,
            )
            with self.conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute(
                    """
                    select r.type, r.visibility, r.owner_open_id, rv.content_text, rv.content_json,
                           kas.eligibility as existing_eligibility,
                           coalesce(kas.metadata->'confirmation', '{}'::jsonb)
                             as existing_confirmation
                    from resources r
                    join resource_versions rv
                      on rv.tenant_id = r.tenant_id and rv.resource_id = r.id
                    left join knowledge_asset_states kas
                      on kas.tenant_id = rv.tenant_id
                     and kas.resource_id = rv.resource_id
                     and kas.resource_version = rv.version
                    where r.tenant_id = %s and r.id = %s and rv.version = %s
                      and (
                        r.owner_open_id = %s
                        or exists (
                          select 1 from resource_permissions rp
                          where rp.tenant_id = r.tenant_id and rp.resource_id = r.id
                            and rp.subject_type = 'user' and rp.subject_id = %s
                            and rp.permission in ('write', 'admin')
                        )
                      )
                    for update of r
                    """,
                    (tenant_id, resource_id, resource_version, actor_open_id, actor_open_id),
                ).fetchone()
                if row is None:
                    raise PermissionError("Exact resource version is not writable by actor")
                if row["type"] == "generated_copy":
                    raise ValueError("generated_copy must be adopted through its lifecycle")
                if row["type"] != "session_snapshot":
                    raise ValueError("only session_snapshot can be manually confirmed")
                stored_snapshot_kind = str(
                    dict(row["content_json"] or {}).get("snapshot_kind") or ""
                ).strip()
                if stored_snapshot_kind not in SESSION_SNAPSHOT_KINDS:
                    raise ValueError("saved session snapshot_kind is invalid")
                requested_snapshot_kind = str(
                    dict(metadata or {}).get("snapshot_kind") or ""
                ).strip()
                if requested_snapshot_kind and requested_snapshot_kind != stored_snapshot_kind:
                    raise ValueError("snapshot_kind does not match the exact saved snapshot")
                confirmation = {
                    "snapshot_kind": stored_snapshot_kind,
                    "confirmed": True,
                    "confirmed_by": actor_open_id,
                }
                confirmation_hash = hashlib.sha256(
                    json.dumps(confirmation, sort_keys=True, ensure_ascii=False).encode("utf-8")
                ).hexdigest()
                existing_confirmation = dict(row["existing_confirmation"] or {})
                existing_eligibility = row["existing_eligibility"]
                if existing_confirmation == confirmation and existing_eligibility == "qualified":
                    return {
                        "resource_id": resource_id,
                        "resource_version": resource_version,
                        "eligibility": "qualified",
                        "asset_kind": "strategy_fact",
                        "idempotent_replay": True,
                    }
                if existing_confirmation == confirmation and existing_eligibility == "pending":
                    self._enqueue_exact(
                        cur,
                        tenant_id=tenant_id,
                        resource_id=resource_id,
                        resource_version=resource_version,
                        topic="knowledge_enrich",
                        suffix=("confirmation", confirmation_hash),
                        requeue_terminal=True,
                    )
                    return {
                        "resource_id": resource_id,
                        "resource_version": resource_version,
                        "eligibility": "pending",
                        "asset_kind": "strategy_fact",
                        "idempotent_replay": True,
                    }
                normalized = normalize_knowledge_text(row["content_text"])
                digest = normalized_hash(normalized)
                cur.execute(
                    """
                    insert into knowledge_asset_states (
                      tenant_id, resource_id, resource_version, eligibility,
                      eligible_for_synthesis, asset_kind, source_kind, source_authority,
                      quality_score, normalized_text, normalized_hash,
                      visibility, owner_open_id, metadata
                    ) values (
                      %s, %s, %s, 'pending', false, 'strategy_fact', 'user_confirmed',
                      '{"origin":"user","validation":"confirmed","provenance":"session","score":0.9}'::jsonb,
                      0.75, %s, %s, %s, %s, jsonb_build_object('confirmation', %s::jsonb)
                    )
                    on conflict (tenant_id, resource_id, resource_version) do update set
                      eligibility = 'pending',
                      asset_kind = 'strategy_fact',
                      source_kind = 'user_confirmed',
                      normalized_text = excluded.normalized_text,
                      normalized_hash = excluded.normalized_hash,
                      metadata = knowledge_asset_states.metadata || excluded.metadata,
                      qualified_at = null,
                      indexed_at = null,
                      updated_at = now()
                    """,
                    (
                        tenant_id, resource_id, resource_version,
                        normalized, digest, row["visibility"], row["owner_open_id"],
                        json.dumps(confirmation, sort_keys=True, ensure_ascii=False),
                    ),
                )
                self._enqueue_exact(
                    cur,
                    tenant_id=tenant_id,
                    resource_id=resource_id,
                    resource_version=resource_version,
                    topic="knowledge_enrich",
                    suffix=("confirmation", confirmation_hash),
                    requeue_terminal=True,
                )
        return {
            "resource_id": resource_id,
            "resource_version": resource_version,
            "eligibility": "pending",
            "asset_kind": "strategy_fact",
            "idempotent_replay": False,
        }

    def _resolve_family(
        self,
        cur,
        *,
        snapshot: KnowledgeSnapshot,
        normalized_text: str,
        digest: str,
    ) -> tuple[str, str, str | None, int | None, float | None]:
        # knowledge_enrich is an at-least-once outbox processor.  Replaying the same
        # immutable resource version must keep its family identity instead of creating
        # an orphan singleton on every retry.
        existing = cur.execute(
            """
            select state.duplicate_family_id::text as family_id,
                   state.duplicate_kind,
                   state.variant_of_resource_id::text as variant_resource_id,
                   state.variant_of_resource_version as variant_resource_version,
                   nullif(state.metadata->>'duplicate_similarity', '')::double precision
                     as duplicate_similarity
            from knowledge_asset_states state
            join knowledge_families family
              on family.tenant_id = state.tenant_id
             and family.id = state.duplicate_family_id
            where state.tenant_id = %s
              and state.resource_id = %s
              and state.resource_version = %s
              and state.normalized_hash = %s
              and state.duplicate_family_id is not null
            """,
            (
                snapshot.tenant_id,
                snapshot.resource_id,
                snapshot.resource_version,
                digest,
            ),
        ).fetchone()
        if existing is not None:
            return (
                existing["family_id"],
                existing["duplicate_kind"] or "singleton",
                existing["variant_resource_id"],
                (
                    None
                    if existing["variant_resource_version"] is None
                    else int(existing["variant_resource_version"])
                ),
                (
                    None
                    if existing["duplicate_similarity"] is None
                    else float(existing["duplicate_similarity"])
                ),
            )

        readable_clause = """
          and (
            live.visibility = 'team'
            or live.owner_open_id = %(owner_open_id)s
            or exists (
              select 1 from resource_permissions rp
              where rp.tenant_id = live.tenant_id
                and rp.resource_id = live.id
                and rp.subject_type = 'user'
                and rp.subject_id = %(owner_open_id)s
                and rp.permission in ('read', 'write', 'admin')
            )
          )
        """
        params = {
            "tenant_id": snapshot.tenant_id,
            "resource_id": snapshot.resource_id,
            "resource_version": snapshot.resource_version,
            "owner_open_id": snapshot.owner_open_id or "",
            "digest": digest,
            "normalized_text": normalized_text,
        }
        exact = cur.execute(
            f"""
            select candidate.duplicate_family_id::text as family_id,
                   family.canonical_resource_id::text as canonical_resource_id,
                   family.canonical_resource_version
            from knowledge_asset_states candidate
            join knowledge_families family
              on family.tenant_id = candidate.tenant_id
             and family.id = candidate.duplicate_family_id
            join resources live
              on live.tenant_id = candidate.tenant_id
             and live.id = candidate.resource_id
             and live.status = 'active'
            where candidate.tenant_id = %(tenant_id)s
              and candidate.normalized_hash = %(digest)s
              and candidate.eligibility = 'qualified'
              and candidate.duplicate_family_id is not null
              and (candidate.resource_id, candidate.resource_version)
                  <> (%(resource_id)s::uuid, %(resource_version)s)
              {readable_clause}
            order by candidate.quality_score desc, candidate.qualified_at, candidate.resource_id
            limit 1
            """,
            params,
        ).fetchone()
        if exact is not None:
            cur.execute(
                "update knowledge_families set family_kind = 'exact', updated_at = now() "
                "where tenant_id = %s and id = %s",
                (snapshot.tenant_id, exact["family_id"]),
            )
            return (
                exact["family_id"], "exact",
                exact["canonical_resource_id"], int(exact["canonical_resource_version"]),
                1.0,
            )

        # `%` is the pg_trgm GIN-indexable candidate operator.  The explicit LOCAL
        # threshold keeps its candidate set aligned with the final similarity check;
        # without it the tenant advisory lock would protect an O(N) scan per asset and
        # turn batch ingestion into O(N²).
        cur.execute("set local pg_trgm.similarity_threshold = '0.9'")
        near = cur.execute(
            f"""
            select candidate.duplicate_family_id::text as family_id,
                   family.canonical_resource_id::text as canonical_resource_id,
                   family.canonical_resource_version,
                   similarity(candidate.normalized_text, %(normalized_text)s) as score
            from knowledge_asset_states candidate
            join knowledge_families family
              on family.tenant_id = candidate.tenant_id
             and family.id = candidate.duplicate_family_id
            join resources live
              on live.tenant_id = candidate.tenant_id
             and live.id = candidate.resource_id
             and live.status = 'active'
            where candidate.tenant_id = %(tenant_id)s
              and candidate.eligibility = 'qualified'
              and candidate.duplicate_family_id is not null
              and candidate.normalized_text <> ''
              and (candidate.resource_id, candidate.resource_version)
                  <> (%(resource_id)s::uuid, %(resource_version)s)
              and candidate.normalized_text OPERATOR(public.%%) %(normalized_text)s
              and similarity(candidate.normalized_text, %(normalized_text)s) >= 0.9
              {readable_clause}
            order by score desc, candidate.quality_score desc, candidate.resource_id
            limit 1
            """,
            params,
        ).fetchone()
        if near is not None:
            cur.execute(
                "update knowledge_families set family_kind = 'near', updated_at = now() "
                "where tenant_id = %s and id = %s",
                (snapshot.tenant_id, near["family_id"]),
            )
            return (
                near["family_id"], "near",
                near["canonical_resource_id"], int(near["canonical_resource_version"]),
                float(near["score"]),
            )

        family = cur.execute(
            """
            insert into knowledge_families (
              tenant_id, canonical_resource_id, canonical_resource_version,
              family_kind, canonical_hash, metadata
            ) values (%s, %s, %s, 'singleton', %s, '{}'::jsonb)
            returning id::text as id
            """,
            (snapshot.tenant_id, snapshot.resource_id, snapshot.resource_version, digest),
        ).fetchone()
        return family["id"], "singleton", None, None, None

    @staticmethod
    def _ensure_family_edge(
        cur,
        *,
        snapshot: KnowledgeSnapshot,
        family_id: str | None,
        duplicate_kind: str | None,
        canonical_resource_id: str | None,
        canonical_resource_version: int | None,
        similarity: float | None,
    ) -> None:
        if (
            duplicate_kind not in {"exact", "near"}
            or family_id is None
            or canonical_resource_id is None
            or canonical_resource_version is None
        ):
            return
        score = 1.0 if duplicate_kind == "exact" else float(similarity or 0.9)
        evidence = (
            "normalized_sha256_equal"
            if duplicate_kind == "exact"
            else "pg_trgm_similarity_gte_0.9"
        )
        properties = {
            "family_id": family_id,
            "match_kind": duplicate_kind,
            "similarity": round(score, 6),
            "evidence": evidence,
            "strength": "strong",
            "system_generated": True,
        }
        cur.execute(
            """
            insert into resource_edges (
              tenant_id,
              source_resource_id, source_resource_version,
              target_resource_id, target_resource_version,
              edge_type, weight, properties
            ) values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (
              tenant_id,
              source_resource_id, source_resource_version,
              target_resource_id, target_resource_version,
              edge_type
            ) do nothing
            """,
            (
                snapshot.tenant_id,
                snapshot.resource_id,
                snapshot.resource_version,
                canonical_resource_id,
                canonical_resource_version,
                "duplicate_of" if duplicate_kind == "exact" else "variant_of",
                score,
                json.dumps(properties, sort_keys=True, ensure_ascii=False),
            ),
        )

    def _ensure_no_island(self, cur, *, snapshot: KnowledgeSnapshot) -> tuple[str, int, bool]:
        existing = cur.execute(
            """
            select 1 from resource_edges
            where tenant_id = %s
              and (
                (source_resource_id = %s and source_resource_version = %s)
                or
                (target_resource_id = %s and target_resource_version = %s)
              )
            limit 1
            """,
            (
                snapshot.tenant_id, snapshot.resource_id, snapshot.resource_version,
                snapshot.resource_id, snapshot.resource_version,
            ),
        ).fetchone()
        if existing is not None or snapshot.resource_type == "knowledge_anchor":
            return "", 0, False
        anchor_id, anchor_version = self._ensure_anchor(cur, tenant_id=snapshot.tenant_id)
        inserted = cur.execute(
            """
            insert into resource_edges (
              tenant_id,
              source_resource_id, source_resource_version,
              target_resource_id, target_resource_version,
              edge_type, weight, properties
            ) values (
              %s, %s, %s, %s, %s, 'belongs_to_knowledge_base', 0.05,
              '{"strength":"weak","system_generated":true}'::jsonb
            )
            on conflict (
              tenant_id,
              source_resource_id, source_resource_version,
              target_resource_id, target_resource_version,
              edge_type
            ) do nothing
            returning id
            """,
            (
                snapshot.tenant_id,
                snapshot.resource_id, snapshot.resource_version,
                anchor_id, anchor_version,
            ),
        ).fetchone()
        return anchor_id, anchor_version, inserted is not None

    def _ensure_anchor(self, cur, *, tenant_id: str) -> tuple[str, int]:
        existing = cur.execute(
            """
            select r.id::text as id, latest.version
            from resources r
            join lateral (
              select rv.version
              from resource_versions rv
              where rv.tenant_id = r.tenant_id and rv.resource_id = r.id
              order by rv.version desc
              limit 1
            ) latest on true
            where r.tenant_id = %s and r.type = 'knowledge_anchor'
            for update of r
            """,
            (tenant_id,),
        ).fetchone()
        if existing is not None:
            return existing["id"], int(existing["version"])
        anchor_id = str(uuid.uuid5(ANCHOR_NAMESPACE, tenant_id))
        content_json = {"system_role": "knowledge_anchor"}
        content_hash = hashlib.sha256(
            ("\n" + json.dumps(content_json, sort_keys=True, ensure_ascii=False)).encode("utf-8")
        ).hexdigest()
        cur.execute(
            """
            insert into resources (
              id, tenant_id, type, title, summary, content_text, content_json,
              status, visibility, owner_open_id
            ) values (
              %s, %s, 'knowledge_anchor', '知识库根节点',
              '系统图根，不参与正文检索', '', %s::jsonb,
              'active', 'team', 'system'
            )
            """,
            (anchor_id, tenant_id, json.dumps(content_json, sort_keys=True, ensure_ascii=False)),
        )
        cur.execute(
            """
            insert into resource_versions (
              tenant_id, resource_id, version, content_hash, content_text, content_json, changed_by
            ) values (%s, %s, 1, %s, '', %s::jsonb, 'knowledge_enrich')
            """,
            (
                tenant_id, anchor_id, content_hash,
                json.dumps(content_json, sort_keys=True, ensure_ascii=False),
            ),
        )
        cur.execute(
            """
            insert into resource_type_counts (tenant_id, type, count)
            values (%s, 'knowledge_anchor', 1)
            on conflict (tenant_id, type) do update
            set count = greatest(resource_type_counts.count, 1), updated_at = now()
            """,
            (tenant_id,),
        )
        return anchor_id, 1

    @staticmethod
    def _enqueue_teardown_dependents(
        cur,
        *,
        snapshot: KnowledgeSnapshot,
        decision: KnowledgeDecision,
        digest: str,
    ) -> None:
        """Reclassify teardowns whenever a source's current-version fact changes."""
        dependents = cur.execute(
            """
            select distinct edge.source_resource_id::text as resource_id,
                            edge.source_resource_version as resource_version
            from resource_edges edge
            join resources dependent
              on dependent.tenant_id = edge.tenant_id
             and dependent.id = edge.source_resource_id
             and dependent.type in ('writing_teardown', 'explosive_teardown', 'xhs_teardown')
            where edge.tenant_id = %s
              and edge.target_resource_id = %s
              and edge.edge_type = 'teardown_of'
            order by resource_id, resource_version
            """,
            (snapshot.tenant_id, snapshot.resource_id),
        ).fetchall()
        dependency_revision = (
            "dependency-source",
            snapshot.resource_id,
            str(snapshot.resource_version),
            str(snapshot.lifecycle_state_version or 0),
            snapshot.status,
            decision.eligibility,
            digest,
        )
        for dependent in dependents:
            KnowledgeRepository._enqueue_exact(
                cur,
                tenant_id=snapshot.tenant_id,
                resource_id=dependent["resource_id"],
                resource_version=int(dependent["resource_version"]),
                topic="knowledge_enrich",
                suffix=dependency_revision,
                requeue_terminal=True,
            )

    @staticmethod
    def _enqueue_exact(
        cur,
        *,
        tenant_id: str,
        resource_id: str,
        resource_version: int,
        topic: str,
        suffix: tuple[str, ...],
        requeue_terminal: bool = False,
        payload_extra: dict[str, Any] | None = None,
    ) -> None:
        identity = [tenant_id, resource_id, resource_version, topic, *suffix]
        dedupe_key = hashlib.sha256(
            json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        conflict_sql = (
            """
            on conflict (tenant_id, dedupe_key) do update set
              status = case
                when resource_outbox.status in ('succeeded', 'superseded', 'dead')
                  then 'pending'
                else resource_outbox.status
              end,
              attempts = case
                when resource_outbox.status in ('succeeded', 'superseded', 'dead') then 0
                else resource_outbox.attempts
              end,
              next_attempt_at = case
                when resource_outbox.status in ('succeeded', 'superseded', 'dead') then now()
                else resource_outbox.next_attempt_at
              end,
              lease_owner = case
                when resource_outbox.status in ('succeeded', 'superseded', 'dead') then null
                else resource_outbox.lease_owner
              end,
              lease_expires_at = case
                when resource_outbox.status in ('succeeded', 'superseded', 'dead') then null
                else resource_outbox.lease_expires_at
              end,
              error_code = case
                when resource_outbox.status in ('succeeded', 'superseded', 'dead') then null
                else resource_outbox.error_code
              end,
              error_summary = case
                when resource_outbox.status in ('succeeded', 'superseded', 'dead') then null
                else resource_outbox.error_summary
              end,
              dead_at = case
                when resource_outbox.status in ('succeeded', 'superseded', 'dead') then null
                else resource_outbox.dead_at
              end,
              updated_at = now()
            """
            if requeue_terminal
            else "on conflict (tenant_id, dedupe_key) do nothing"
        )
        payload = {
            "resource_id": resource_id,
            "version": resource_version,
            **dict(payload_extra or {}),
        }
        cur.execute(
            f"""
            insert into resource_outbox (
              tenant_id, resource_id, resource_version, topic, dedupe_key, payload
            ) values (
              %s, %s, %s, %s, %s, %s::jsonb
            )
            {conflict_sql}
            """,
            (
                tenant_id, resource_id, resource_version, topic, dedupe_key,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ),
        )

    @staticmethod
    def _synthesis_actor_ids(cur, *, snapshot: KnowledgeSnapshot) -> tuple[str, ...]:
        """Return actors whose currently readable pattern inputs may have changed."""
        actors: set[str] = set()
        if snapshot.owner_open_id:
            actors.add(snapshot.owner_open_id)
        permission_rows = cur.execute(
            """
            select distinct subject_id
            from resource_permissions
            where tenant_id = %s and resource_id = %s
              and subject_type = 'user'
              and permission in ('read', 'write', 'admin')
            """,
            (snapshot.tenant_id, snapshot.resource_id),
        ).fetchall()
        actors.update(str(row["subject_id"]) for row in permission_rows if row["subject_id"])
        prior_consumers = cur.execute(
            """
            select distinct pattern.owner_open_id
            from resource_edges edge
            join resources pattern
              on pattern.tenant_id = edge.tenant_id
             and pattern.id = edge.source_resource_id
             and pattern.type = 'writing_pattern'
            where edge.tenant_id = %s
              and edge.target_resource_id = %s
              and pattern.owner_open_id is not null
            """,
            (snapshot.tenant_id, snapshot.resource_id),
        ).fetchall()
        actors.update(
            str(row["owner_open_id"])
            for row in prior_consumers
            if row["owner_open_id"]
        )
        if snapshot.status == "active" and snapshot.visibility == "team":
            profile_rows = cur.execute(
                """
                select owner_open_id from writing_profile_states where tenant_id = %s
                """,
                (snapshot.tenant_id,),
            ).fetchall()
            actors.update(
                str(row["owner_open_id"])
                for row in profile_rows
                if row["owner_open_id"]
            )
        return tuple(sorted(actors))

    @staticmethod
    def _enqueue_embedding(
        cur,
        *,
        tenant_id: str,
        resource_id: str,
        resource_version: int,
        embedding_index_id: str,
        chunker_version: str,
    ) -> None:
        dedupe_key = json.dumps(
            [tenant_id, "embedding_generate", embedding_index_id, resource_id, resource_version],
            ensure_ascii=False,
            sort_keys=True,
        )
        payload = {
            "resource_id": resource_id,
            "version": resource_version,
            "embedding_index_id": embedding_index_id,
            "chunker_version": chunker_version,
        }
        cur.execute(
            """
            insert into resource_outbox (
              tenant_id, resource_id, resource_version, topic, dedupe_key, payload
            ) values (%s, %s, %s, 'embedding_generate', %s, %s::jsonb)
            on conflict (tenant_id, dedupe_key) do nothing
            """,
            (
                tenant_id, resource_id, resource_version, dedupe_key,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ),
        )
