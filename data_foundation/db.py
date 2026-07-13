from __future__ import annotations

import os
from contextlib import contextmanager
from importlib import resources
from typing import Any, Iterator

import psycopg
from psycopg import Connection
from psycopg import sql
from psycopg.rows import dict_row


DATA_FOUNDATION_TABLES = (
    "data_foundation_migrations",
    "writing_profile_states",
    "preference_synthesis_events",
    "preference_synthesis_states",
    "preference_observations",
    "knowledge_enrichments",
    "knowledge_asset_states",
    "knowledge_families",
    "user_skill_audit_events",
    "user_skill_publications",
    "user_skill_versions",
    "user_skills",
    "user_skill_revisions",
    "service_error_aggregates",
    "sync_runs",
    "service_executions",
    "service_instances",
    "sync_sources",
    "generated_copy_states",
    "resource_outbox",
    "resource_embeddings",
    "embedding_indexes",
    "resource_edges",
    "resource_permissions",
    "resource_events",
    "resource_versions",
    "resource_mappings",
    "resource_type_counts",
    "resources",
)

DATA_FOUNDATION_VIEWS = (
    "current_knowledge_targets",
    "base_current_knowledge_targets",
    "qualified_knowledge_versions",
)

KNOWLEDGE_GATE_MIGRATION_KEY = "20260713_knowledge_gate_v2"


def database_url() -> str:
    url = os.environ.get("XHS_DATABASE_URL")
    if not url:
        raise RuntimeError("XHS_DATABASE_URL is required for Phase 3 data foundation")
    return url


def connect(url: str | None = None, **kwargs: Any) -> Connection:
    return psycopg.connect(url or database_url(), row_factory=dict_row, **kwargs)


def run_migrations(conn: Connection) -> None:
    # DDL/view switch and the synchronous knowledge qualification gate must become
    # visible atomically.  In particular, an autocommit caller must not expose the new
    # current_knowledge_targets view before legacy resources have exact states.
    with conn.transaction():
        _apply_migrations(conn)
        _complete_knowledge_gate(conn)


def _apply_migrations(conn: Connection) -> None:
    schema_sql = resources.files("data_foundation").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.execute(schema_sql)


def _knowledge_gate_targets(conn: Connection) -> list[dict[str, Any]]:
    """Return the exact pre-existing versions that must be classified before cutover."""
    with conn.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(
            """
            select r.tenant_id,
                   r.id::text as resource_id,
                   case
                     when r.type = 'generated_copy' then gcs.knowledge_target_version
                     else (
                       select max(rv.version)
                       from resource_versions rv
                       where rv.tenant_id = r.tenant_id and rv.resource_id = r.id
                     )
                   end as resource_version
            from resources r
            left join generated_copy_states gcs
              on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
            where r.type <> 'knowledge_anchor'
            order by r.tenant_id,
                     case
                       when r.type in ('writing_teardown', 'explosive_teardown', 'xhs_teardown') then 1
                       when r.type = 'writing_pattern' then 2
                       else 0
                     end,
                     r.id
            """
        ).fetchall()
    return [
        dict(row)
        for row in rows
        if row["resource_version"] is not None
    ]


def _complete_knowledge_gate(conn: Connection) -> None:
    """Synchronously qualify legacy exact versions before the new view is committed.

    The schema migration records a transient ``backfilling`` marker.  Because this
    function runs in the same transaction as schema.sql, readers see either the old
    schema or the fully qualified new schema—never an empty knowledge window.  Any
    classification/integrity failure aborts the whole migration and is retried on the
    next startup; there is no permanent legacy fallback branch.
    """
    with conn.cursor(row_factory=dict_row) as cursor:
        marker = cursor.execute(
            """
            select status
            from data_foundation_migrations
            where migration_key = %s
            for update
            """,
            (KNOWLEDGE_GATE_MIGRATION_KEY,),
        ).fetchone()
    if marker is None or marker["status"] != "backfilling":
        return

    from data_foundation.knowledge.service import KnowledgeService

    service = KnowledgeService(conn)
    targets = _knowledge_gate_targets(conn)
    for target in targets:
        service.enrich_exact_version(
            tenant_id=target["tenant_id"],
            resource_id=target["resource_id"],
            resource_version=int(target["resource_version"]),
        )

    # Final qualification means every exact migration target has an explicit state,
    # including deterministic rejections.  A missing state must fail the cutover.
    missing: list[tuple[str, str, int]] = []
    with conn.cursor(row_factory=dict_row) as cursor:
        for target in targets:
            state = cursor.execute(
                """
                select eligibility
                from knowledge_asset_states
                where tenant_id = %s and resource_id = %s and resource_version = %s
                """,
                (
                    target["tenant_id"],
                    target["resource_id"],
                    int(target["resource_version"]),
                ),
            ).fetchone()
            if state is None:
                missing.append(
                    (
                        target["tenant_id"],
                        target["resource_id"],
                        int(target["resource_version"]),
                    )
                )
        if missing:
            raise RuntimeError(
                f"knowledge qualification gate left {len(missing)} exact target(s) unclassified"
            )
        cursor.execute(
            """
            update data_foundation_migrations
            set status = 'complete', completed_at = now()
            where migration_key = %s and status = 'backfilling'
            """,
            (KNOWLEDGE_GATE_MIGRATION_KEY,),
        )


def reset_data_foundation(conn: Connection) -> None:
    with conn.transaction():
        for name in DATA_FOUNDATION_VIEWS:
            conn.execute(sql.SQL("drop view if exists {}").format(sql.Identifier(name)))
        for name in DATA_FOUNDATION_TABLES:
            conn.execute(sql.SQL("drop table if exists {}").format(sql.Identifier(name)))
        _apply_migrations(conn)
        _complete_knowledge_gate(conn)


@contextmanager
def transaction(conn: Connection) -> Iterator[Connection]:
    with conn.transaction():
        yield conn
