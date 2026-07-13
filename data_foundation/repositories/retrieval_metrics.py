from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from typing import Any
import uuid

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.permissions import readable_resource_by_actor_key_where
from data_foundation.repositories.base import BaseRepository


RETRIEVAL_MODES = frozenset(
    {"hybrid", "semantic_only", "keyword_only", "insufficient_relevance"}
)
RETRIEVAL_OUTCOMES = frozenset({"success", "error"})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
EXPLICIT_ADOPTION_WINDOW_DAYS = 7
COMMITTED_USE_WINDOW_DAYS = 14
DEFAULT_MIN_SAMPLE_SIZE = 5


def exact_evidence_key(tenant_id: str, resource_id: str, resource_version: int) -> str:
    """Fingerprint one tenant-scoped immutable evidence identity."""

    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    tenant_id = tenant_id.strip()
    canonical_id = str(uuid.UUID(str(resource_id)))
    if (
        not isinstance(resource_version, int)
        or isinstance(resource_version, bool)
        or resource_version <= 0
    ):
        raise ValueError("resource_version must be a positive integer")
    value = f"{tenant_id}:{canonical_id}:{resource_version}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def retrieval_payload_key(measurement: "RetrievalMeasurement") -> str:
    """Fingerprint the complete safe result projection, excluding timing fields."""

    payload = {
        "outcome": measurement.outcome,
        "retrieval_mode": measurement.retrieval_mode,
        "engine_count": measurement.engine_count,
        "degraded_engine_count": measurement.degraded_engine_count,
        "exposures": [
            {
                "evidence_key": exposure.evidence_key,
                "rank": exposure.rank,
                "score": exposure.score,
                "relevance": exposure.relevance,
                "quality": exposure.quality,
                "freshness": exposure.freshness,
                "performance": exposure.performance,
                "recalled_by_semantic": exposure.recalled_by_semantic,
                "recalled_by_keyword": exposure.recalled_by_keyword,
                "recalled_by_graph": exposure.recalled_by_graph,
            }
            for exposure in sorted(
                measurement.exposures,
                key=lambda item: (item.rank, item.evidence_key),
            )
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RetrievalExposure:
    evidence_key: str
    rank: int
    score: float
    relevance: float
    quality: float
    freshness: float
    performance: float
    recalled_by_semantic: bool
    recalled_by_keyword: bool
    recalled_by_graph: bool


@dataclass(frozen=True)
class RetrievalMeasurement:
    tenant_id: str
    actor_key: str
    thread_key: str | None
    run_key: str
    turn_key: str
    tool_call_key: str
    outcome: str
    retrieval_mode: str | None
    engine_count: int
    degraded_engine_count: int
    latency_ms: int
    observed_at: datetime
    exposures: tuple[RetrievalExposure, ...]


@dataclass(frozen=True)
class RecordedRetrieval:
    retrieval_run_id: str
    evidence_count: int
    inserted: bool


@dataclass(frozen=True)
class RetrievalOutcomeMetrics:
    retrieval_run_count: int
    successful_run_count: int
    error_run_count: int
    hybrid_run_count: int
    semantic_only_run_count: int
    keyword_only_run_count: int
    insufficient_relevance_run_count: int
    error_rate: float | None
    degraded_run_count: int
    degraded_run_rate: float | None
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    latency_p99_ms: int | None
    evidence_exposure_count: int
    unique_evidence_exposure_count: int
    attributed_copy_count: int
    mature_explicit_copy_count: int
    explicit_adopted_copy_count: int | None
    censored_explicit_copy_count: int
    mature_committed_copy_count: int
    committed_use_copy_count: int | None
    censored_committed_copy_count: int
    published_copy_count: int | None
    explicit_adoption_rate: float | None
    committed_use_rate: float | None
    sample_suppressed: bool


class RetrievalMetricsRepository(BaseRepository):
    """Persist safe retrieval facts and derive lifecycle outcomes.

    The run and exposure tables contain no query, content, open_id or resource
    identity. Exact identities live only in a tenant-scoped internal map populated
    after the same current-knowledge and ACL gate used by retrieval. Aggregation can
    therefore use indexed joins without hashing every resource version at report time.
    """

    def __init__(self, conn: Connection):
        super().__init__(conn)

    def record(
        self,
        measurement: RetrievalMeasurement,
        *,
        exact_identities: dict[str, tuple[str, int]],
    ) -> RecordedRetrieval:
        self._validate_measurement(measurement)
        evidence_rows = self._validated_evidence_rows(measurement, exact_identities)
        readable = readable_resource_by_actor_key_where("evidence_resource")
        with self.connection_context() as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    candidate_run_id = str(uuid.uuid4())
                    payload_key = retrieval_payload_key(measurement)
                    stored = cursor.execute(
                        """
                        insert into knowledge_retrieval_runs (
                          id, tenant_id, actor_key, thread_key, run_key, turn_key,
                          tool_call_key, payload_key, outcome, retrieval_mode,
                          evidence_count, engine_count, degraded_engine_count,
                          latency_ms, created_at
                        ) values (
                          %(candidate_run_id)s::uuid, %(tenant_id)s, %(actor_key)s,
                          %(thread_key)s, %(run_key)s, %(turn_key)s,
                          %(tool_call_key)s, %(payload_key)s, %(outcome)s,
                          %(retrieval_mode)s, 0, %(engine_count)s,
                          %(degraded_engine_count)s, %(latency_ms)s,
                          %(observed_at)s
                        )
                        on conflict (tenant_id, actor_key, tool_call_key) do update
                          set created_at = case
                                when knowledge_retrieval_runs.payload_key
                                       = excluded.payload_key
                                then least(
                                  knowledge_retrieval_runs.created_at,
                                  excluded.created_at
                                )
                                else knowledge_retrieval_runs.created_at
                              end,
                              latency_ms = case
                                when knowledge_retrieval_runs.payload_key
                                       = excluded.payload_key
                                 and excluded.created_at
                                       < knowledge_retrieval_runs.created_at
                                then excluded.latency_ms
                                else knowledge_retrieval_runs.latency_ms
                              end
                        returning id::text, evidence_count, payload_key, created_at
                        """,
                        {
                            "candidate_run_id": candidate_run_id,
                            "tenant_id": measurement.tenant_id,
                            "actor_key": measurement.actor_key,
                            "thread_key": measurement.thread_key,
                            "run_key": measurement.run_key,
                            "turn_key": measurement.turn_key,
                            "tool_call_key": measurement.tool_call_key,
                            "payload_key": payload_key,
                            "outcome": measurement.outcome,
                            "retrieval_mode": measurement.retrieval_mode,
                            "engine_count": measurement.engine_count,
                            "degraded_engine_count": measurement.degraded_engine_count,
                            "latency_ms": measurement.latency_ms,
                            "observed_at": measurement.observed_at,
                        },
                    ).fetchone()
                    inserted = str(stored["id"]) == candidate_run_id
                    if not inserted:
                        if str(stored["payload_key"]) != payload_key:
                            raise ValueError("conflicting retrieval measurement replay")
                        cursor.execute(
                            """
                            update knowledge_retrieval_exposures
                            set created_at = least(created_at, %s)
                            where tenant_id = %s and retrieval_run_id = %s::uuid
                            """,
                            (
                                measurement.observed_at,
                                measurement.tenant_id,
                                stored["id"],
                            ),
                        )
                        return RecordedRetrieval(
                            retrieval_run_id=str(stored["id"]),
                            evidence_count=int(stored["evidence_count"]),
                            inserted=False,
                        )

                    retrieval_run_id = str(stored["id"])
                    mapped_keys: set[str] = set()
                    if evidence_rows:
                        mapped_keys = {
                            str(row["evidence_key"])
                            for row in cursor.execute(
                                f"""
                                with candidates(
                                  evidence_key, resource_id, resource_version
                                ) as (
                                  select * from unnest(
                                    %(evidence_keys)s::text[],
                                    %(resource_ids)s::uuid[],
                                    %(resource_versions)s::int[]
                                  )
                                )
                                insert into knowledge_retrieval_evidence_keys (
                                  tenant_id, evidence_key, resource_id,
                                  resource_version, first_verified_at,
                                  last_verified_at
                                )
                                select %(tenant_id)s, candidate.evidence_key,
                                       target.resource_id, target.resource_version,
                                       now(), now()
                                from candidates candidate
                                join current_knowledge_targets target
                                  on target.tenant_id = %(tenant_id)s
                                 and target.resource_id = candidate.resource_id
                                 and target.resource_version
                                       = candidate.resource_version
                                join resources evidence_resource
                                  on evidence_resource.tenant_id = target.tenant_id
                                 and evidence_resource.id = target.resource_id
                                where {readable}
                                order by candidate.evidence_key
                                on conflict (tenant_id, evidence_key) do update
                                  set last_verified_at = excluded.last_verified_at
                                  where knowledge_retrieval_evidence_keys.resource_id
                                          = excluded.resource_id
                                    and knowledge_retrieval_evidence_keys.resource_version
                                          = excluded.resource_version
                                returning evidence_key
                                """,
                                {
                                    "tenant_id": measurement.tenant_id,
                                    "actor_key": measurement.actor_key,
                                    "evidence_keys": [
                                        row["evidence_key"] for row in evidence_rows
                                    ],
                                    "resource_ids": [
                                        row["resource_id"] for row in evidence_rows
                                    ],
                                    "resource_versions": [
                                        row["resource_version"] for row in evidence_rows
                                    ],
                                },
                            ).fetchall()
                        }
                    admitted = [
                        row
                        for row in evidence_rows
                        if row["evidence_key"] in mapped_keys
                    ]
                    if admitted:
                        cursor.execute(
                            """
                            with candidates(
                              evidence_key, rank, score, relevance, quality,
                              freshness, performance, recalled_by_semantic,
                              recalled_by_keyword, recalled_by_graph
                            ) as (
                              select * from unnest(
                                %(evidence_keys)s::text[], %(ranks)s::int[],
                                %(scores)s::float8[], %(relevances)s::float8[],
                                %(qualities)s::float8[], %(freshnesses)s::float8[],
                                %(performances)s::float8[],
                                %(semantic_flags)s::boolean[],
                                %(keyword_flags)s::boolean[],
                                %(graph_flags)s::boolean[]
                              )
                            )
                            insert into knowledge_retrieval_exposures (
                              tenant_id, retrieval_run_id, evidence_key, rank,
                              score, relevance, quality, freshness, performance,
                              recalled_by_semantic, recalled_by_keyword,
                              recalled_by_graph, created_at
                            )
                            select %(tenant_id)s, %(retrieval_run_id)s::uuid,
                                   candidate.evidence_key, candidate.rank,
                                   candidate.score, candidate.relevance,
                                   candidate.quality, candidate.freshness,
                                   candidate.performance,
                                   candidate.recalled_by_semantic,
                                   candidate.recalled_by_keyword,
                                   candidate.recalled_by_graph, %(observed_at)s
                            from candidates candidate
                            order by candidate.evidence_key
                            on conflict (
                              tenant_id, retrieval_run_id, evidence_key
                            ) do nothing
                            """,
                            {
                                "tenant_id": measurement.tenant_id,
                                "retrieval_run_id": retrieval_run_id,
                                "observed_at": measurement.observed_at,
                                "evidence_keys": [
                                    row["evidence_key"] for row in admitted
                                ],
                                "ranks": [row["rank"] for row in admitted],
                                "scores": [row["score"] for row in admitted],
                                "relevances": [
                                    row["relevance"] for row in admitted
                                ],
                                "qualities": [row["quality"] for row in admitted],
                                "freshnesses": [
                                    row["freshness"] for row in admitted
                                ],
                                "performances": [
                                    row["performance"] for row in admitted
                                ],
                                "semantic_flags": [
                                    row["recalled_by_semantic"] for row in admitted
                                ],
                                "keyword_flags": [
                                    row["recalled_by_keyword"] for row in admitted
                                ],
                                "graph_flags": [
                                    row["recalled_by_graph"] for row in admitted
                                ],
                            },
                        )
                    count_row = cursor.execute(
                        """
                        update knowledge_retrieval_runs run
                        set evidence_count = (
                          select count(*)
                          from knowledge_retrieval_exposures exposure
                          where exposure.tenant_id = run.tenant_id
                            and exposure.retrieval_run_id = run.id
                        )
                        where run.tenant_id = %s and run.id = %s::uuid
                        returning evidence_count
                        """,
                        (measurement.tenant_id, retrieval_run_id),
                    ).fetchone()
                    return RecordedRetrieval(
                        retrieval_run_id=retrieval_run_id,
                        evidence_count=int(count_row["evidence_count"]),
                        inserted=True,
                    )

    @staticmethod
    def _validated_evidence_rows(
        measurement: RetrievalMeasurement,
        exact_identities: dict[str, tuple[str, int]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for exposure in sorted(
            measurement.exposures,
            key=lambda item: item.evidence_key,
        ):
            exact_identity = exact_identities.get(exposure.evidence_key)
            if exact_identity is None:
                raise ValueError("exact evidence identity is required for ACL gating")
            resource_id, resource_version = exact_identity
            canonical_id = str(uuid.UUID(str(resource_id)))
            if exposure.evidence_key != exact_evidence_key(
                measurement.tenant_id,
                canonical_id,
                resource_version,
            ):
                raise ValueError("exact evidence identity does not match fingerprint")
            rows.append(
                {
                    "evidence_key": exposure.evidence_key,
                    "resource_id": canonical_id,
                    "resource_version": resource_version,
                    "rank": exposure.rank,
                    "score": exposure.score,
                    "relevance": exposure.relevance,
                    "quality": exposure.quality,
                    "freshness": exposure.freshness,
                    "performance": exposure.performance,
                    "recalled_by_semantic": exposure.recalled_by_semantic,
                    "recalled_by_keyword": exposure.recalled_by_keyword,
                    "recalled_by_graph": exposure.recalled_by_graph,
                }
            )
        return rows

    def delete_expired(self, *, older_than: datetime, limit: int) -> int:
        """Delete one locked batch of raw runs and then remove orphan identity keys."""

        if older_than.tzinfo is None or older_than.utcoffset() is None:
            raise ValueError("older_than must include a timezone")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        with self.connection_context() as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    expired = cursor.execute(
                        """
                        select run.id
                        from knowledge_retrieval_runs run
                        where run.created_at < %s
                        order by run.created_at, run.id
                        limit %s
                        for update skip locked
                        """,
                        (older_than, limit),
                    ).fetchall()
                    if not expired:
                        return 0
                    run_ids = [str(row["id"]) for row in expired]
                    return self._delete_runs_and_orphans(cursor, run_ids)

    @staticmethod
    def _delete_runs_and_orphans(cursor: Any, run_ids: list[str]) -> int:
        if not run_ids:
            return 0
        exposure_rows = cursor.execute(
            """
            select exposure.retrieval_run_id::text, exposure.tenant_id,
                   exposure.evidence_key
            from knowledge_retrieval_exposures exposure
            where exposure.retrieval_run_id = any(%s::uuid[])
            order by exposure.tenant_id, exposure.evidence_key,
                     exposure.retrieval_run_id
            """,
            (run_ids,),
        ).fetchall()
        affected_keys = sorted(
            {
                (str(row["tenant_id"]), str(row["evidence_key"]))
                for row in exposure_rows
            }
        )
        locked_keys: set[tuple[str, str]] = set()
        if affected_keys:
            locked_keys = {
                (str(row["tenant_id"]), str(row["evidence_key"]))
                for row in cursor.execute(
                    """
                    with candidates(tenant_id, evidence_key) as (
                      select * from unnest(%s::text[], %s::text[])
                    )
                    select identity.tenant_id, identity.evidence_key
                    from knowledge_retrieval_evidence_keys identity
                    join candidates candidate
                      on candidate.tenant_id = identity.tenant_id
                     and candidate.evidence_key = identity.evidence_key
                    order by identity.tenant_id, identity.evidence_key
                    for update of identity skip locked
                    """,
                    (
                        [key[0] for key in affected_keys],
                        [key[1] for key in affected_keys],
                    ),
                ).fetchall()
            }
        unlocked_by_run = {
            str(row["retrieval_run_id"])
            for row in exposure_rows
            if (str(row["tenant_id"]), str(row["evidence_key"]))
            not in locked_keys
        }
        eligible_run_ids = [
            run_id for run_id in run_ids if run_id not in unlocked_by_run
        ]
        if not eligible_run_ids:
            return 0
        eligible_keys = sorted(
            {
                (str(row["tenant_id"]), str(row["evidence_key"]))
                for row in exposure_rows
                if str(row["retrieval_run_id"]) in eligible_run_ids
            }
        )
        deleted = cursor.execute(
            """
            delete from knowledge_retrieval_runs
            where id = any(%s::uuid[])
            returning id
            """,
            (eligible_run_ids,),
        ).fetchall()
        if eligible_keys:
            cursor.execute(
                """
                with affected(tenant_id, evidence_key) as (
                  select * from unnest(%s::text[], %s::text[])
                )
                delete from knowledge_retrieval_evidence_keys identity
                using affected
                where identity.tenant_id = affected.tenant_id
                  and identity.evidence_key = affected.evidence_key
                  and not exists (
                    select 1
                    from knowledge_retrieval_exposures exposure
                    where exposure.tenant_id = identity.tenant_id
                      and exposure.evidence_key = identity.evidence_key
                  )
                """,
                (
                    [key[0] for key in eligible_keys],
                    [key[1] for key in eligible_keys],
                ),
            )
        return len(deleted)

    def aggregate(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        as_of: datetime | None = None,
        min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    ) -> RetrievalOutcomeMetrics:
        tenant_id = self._required_text(tenant_id, "tenant_id")
        actor_open_id = self._required_text(actor_open_id, "actor_open_id")
        as_of = as_of or datetime.now(UTC)
        self._validate_bounds(since=since, until=until, as_of=as_of)
        if (
            not isinstance(min_sample_size, int)
            or isinstance(min_sample_size, bool)
            or not 1 <= min_sample_size <= 1000
        ):
            raise ValueError("min_sample_size must be between 1 and 1000")

        time_clauses: list[str] = []
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "actor_open_id": actor_open_id,
            "actor_key": self.actor_key(tenant_id, actor_open_id),
            "as_of": as_of,
        }
        if since is not None:
            time_clauses.append("and run.created_at >= %(since)s")
            params["since"] = since
        if until is not None:
            time_clauses.append("and run.created_at < %(until)s")
            params["until"] = until

        with self.connection_context() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                summary = cursor.execute(
                    self._aggregate_ctes("\n".join(time_clauses))
                    + self._summary_sql(),
                    params,
                ).fetchone()

        total = int(summary["retrieval_run_count"] or 0)
        successful = int(summary["successful_run_count"] or 0)
        errors = int(summary["error_run_count"] or 0)
        degraded = int(summary["degraded_run_count"] or 0)
        attributed = int(summary["attributed_copy_count"] or 0)
        mature_explicit = int(summary["mature_explicit_copy_count"] or 0)
        explicit = int(summary["explicit_adopted_copy_count"] or 0)
        mature_committed = int(summary["mature_committed_copy_count"] or 0)
        committed = int(summary["committed_use_copy_count"] or 0)
        suppressed = min(mature_explicit, mature_committed) < min_sample_size
        return RetrievalOutcomeMetrics(
            retrieval_run_count=total,
            successful_run_count=successful,
            error_run_count=errors,
            hybrid_run_count=int(summary["hybrid_run_count"] or 0),
            semantic_only_run_count=int(summary["semantic_only_run_count"] or 0),
            keyword_only_run_count=int(summary["keyword_only_run_count"] or 0),
            insufficient_relevance_run_count=int(
                summary["insufficient_relevance_run_count"] or 0
            ),
            error_rate=round(errors / total, 6) if total else None,
            degraded_run_count=degraded,
            degraded_run_rate=(
                round(degraded / successful, 6) if successful else None
            ),
            latency_p50_ms=self._optional_int(summary["latency_p50_ms"]),
            latency_p95_ms=self._optional_int(summary["latency_p95_ms"]),
            latency_p99_ms=self._optional_int(summary["latency_p99_ms"]),
            evidence_exposure_count=int(summary["evidence_exposure_count"] or 0),
            unique_evidence_exposure_count=int(
                summary["unique_evidence_exposure_count"] or 0
            ),
            attributed_copy_count=attributed,
            mature_explicit_copy_count=mature_explicit,
            explicit_adopted_copy_count=(
                explicit if mature_explicit >= min_sample_size else None
            ),
            censored_explicit_copy_count=max(attributed - mature_explicit, 0),
            mature_committed_copy_count=mature_committed,
            committed_use_copy_count=(
                committed if mature_committed >= min_sample_size else None
            ),
            censored_committed_copy_count=max(attributed - mature_committed, 0),
            published_copy_count=(
                int(summary["published_copy_count"] or 0)
                if mature_committed >= min_sample_size
                else None
            ),
            explicit_adoption_rate=(
                round(explicit / mature_explicit, 6)
                if mature_explicit >= min_sample_size
                else None
            ),
            committed_use_rate=(
                round(committed / mature_committed, 6)
                if mature_committed >= min_sample_size
                else None
            ),
            sample_suppressed=suppressed,
        )

    def _aggregate_ctes(self, time_clauses: str) -> str:
        readable = self.readable_resource_where("evidence_resource")
        return f"""
        with scoped_runs as materialized (
          select run.id, run.turn_key, run.outcome, run.retrieval_mode,
                 run.degraded_engine_count, run.latency_ms, run.created_at
          from knowledge_retrieval_runs run
          where run.tenant_id = %(tenant_id)s
            and run.actor_key = %(actor_key)s
            and run.created_at <= %(as_of)s
            {time_clauses}
        ),
        scoped_exposures as materialized (
          select exposure.retrieval_run_id,
                 exposure.evidence_key,
                 run.turn_key,
                 run.created_at as retrieved_at,
                 identity.resource_id,
                 identity.resource_version
          from scoped_runs run
          join knowledge_retrieval_exposures exposure
            on exposure.tenant_id = %(tenant_id)s
           and exposure.retrieval_run_id = run.id
          join knowledge_retrieval_evidence_keys identity
            on identity.tenant_id = exposure.tenant_id
           and identity.evidence_key = exposure.evidence_key
          join resources evidence_resource
            on evidence_resource.tenant_id = identity.tenant_id
           and evidence_resource.id = identity.resource_id
          where {readable}
        ),
        attributed_evidence as materialized (
          select exposure.evidence_key,
                 copy_state.resource_id as copy_resource_id,
                 provenance_edge.source_resource_version as copy_resource_version,
                 min(exposure.retrieved_at) as cohort_at
          from scoped_exposures exposure
          join generated_copy_states copy_state
            on copy_state.tenant_id = %(tenant_id)s
           and copy_state.owner_open_id = %(actor_open_id)s
           and copy_state.origin_turn_id is not null
           and encode(digest(copy_state.origin_turn_id, 'sha256'), 'hex')
                 = exposure.turn_key
          join resources copy_resource
            on copy_resource.tenant_id = copy_state.tenant_id
           and copy_resource.id = copy_state.resource_id
           and copy_resource.type = 'generated_copy'
           and copy_resource.status = 'active'
           and copy_resource.owner_open_id = %(actor_open_id)s
          join resource_edges provenance_edge
            on provenance_edge.tenant_id = %(tenant_id)s
           and provenance_edge.source_resource_id = copy_state.resource_id
           and provenance_edge.target_resource_id = exposure.resource_id
           and provenance_edge.target_resource_version = exposure.resource_version
           and provenance_edge.edge_type in ('derived_from', 'imitated_from')
          group by exposure.evidence_key, copy_state.resource_id,
                   provenance_edge.source_resource_version
        ),
        copy_cohorts as materialized (
          select copy_resource_id, min(cohort_at) as cohort_at
          from attributed_evidence
          group by copy_resource_id
        ),
        copy_outcomes as materialized (
          select cohort.copy_resource_id,
                 cohort.cohort_at,
                 explicit_event.occurred_at as explicit_adopted_at,
                 committed_event.occurred_at as committed_at,
                 published_event.occurred_at as published_at
          from copy_cohorts cohort
          left join lateral (
            select min(event.created_at) as occurred_at
            from resource_events event
            where event.tenant_id = %(tenant_id)s
              and event.resource_id = cohort.copy_resource_id
              and event.actor_open_id = %(actor_open_id)s
              and event.event_type = 'adopted'
              and event.created_at >= cohort.cohort_at
              and event.created_at <= %(as_of)s
              and exists (
                select 1
                from attributed_evidence exact_provenance
                where exact_provenance.copy_resource_id
                        = cohort.copy_resource_id
                  and event.payload->'version'
                        = to_jsonb(exact_provenance.copy_resource_version)
              )
          ) explicit_event on true
          left join lateral (
            select min(event.created_at) as occurred_at
            from resource_events event
            where event.tenant_id = %(tenant_id)s
              and event.resource_id = cohort.copy_resource_id
              and event.actor_open_id = %(actor_open_id)s
              and event.event_type in (
                'adopted', 'finalized_for_schedule', 'published'
              )
              and event.created_at >= cohort.cohort_at
              and event.created_at <= %(as_of)s
              and exists (
                select 1
                from attributed_evidence exact_provenance
                where exact_provenance.copy_resource_id
                        = cohort.copy_resource_id
                  and event.payload->'version'
                        = to_jsonb(exact_provenance.copy_resource_version)
              )
          ) committed_event on true
          left join lateral (
            select min(event.created_at) as occurred_at
            from resource_events event
            where event.tenant_id = %(tenant_id)s
              and event.resource_id = cohort.copy_resource_id
              and event.actor_open_id = %(actor_open_id)s
              and event.event_type = 'published'
              and event.created_at >= cohort.cohort_at
              and event.created_at <= %(as_of)s
              and exists (
                select 1
                from attributed_evidence exact_provenance
                where exact_provenance.copy_resource_id
                        = cohort.copy_resource_id
                  and event.payload->'version'
                        = to_jsonb(exact_provenance.copy_resource_version)
              )
          ) published_event on true
        )
        """

    @staticmethod
    def _summary_sql() -> str:
        return f"""
        select
          (select count(*) from scoped_runs) as retrieval_run_count,
          (select count(*) from scoped_runs where outcome = 'success')
            as successful_run_count,
          (select count(*) from scoped_runs where outcome = 'error')
            as error_run_count,
          (select count(*) from scoped_runs where retrieval_mode = 'hybrid')
            as hybrid_run_count,
          (select count(*) from scoped_runs where retrieval_mode = 'semantic_only')
            as semantic_only_run_count,
          (select count(*) from scoped_runs where retrieval_mode = 'keyword_only')
            as keyword_only_run_count,
          (select count(*) from scoped_runs
            where retrieval_mode = 'insufficient_relevance')
            as insufficient_relevance_run_count,
          (select count(*) from scoped_runs
            where outcome = 'success' and degraded_engine_count > 0)
            as degraded_run_count,
          (select percentile_disc(0.50) within group (order by latency_ms)
             from scoped_runs) as latency_p50_ms,
          (select percentile_disc(0.95) within group (order by latency_ms)
             from scoped_runs) as latency_p95_ms,
          (select percentile_disc(0.99) within group (order by latency_ms)
             from scoped_runs) as latency_p99_ms,
          (select count(*) from scoped_exposures) as evidence_exposure_count,
          (select count(distinct (turn_key, evidence_key)) from scoped_exposures)
            as unique_evidence_exposure_count,
          (select count(*) from copy_cohorts) as attributed_copy_count,
          (select count(*) from copy_outcomes
            where cohort_at <= %(as_of)s
              - interval '{EXPLICIT_ADOPTION_WINDOW_DAYS} days')
            as mature_explicit_copy_count,
          (select count(*) from copy_outcomes
            where cohort_at <= %(as_of)s
              - interval '{EXPLICIT_ADOPTION_WINDOW_DAYS} days'
              and explicit_adopted_at <= cohort_at
                + interval '{EXPLICIT_ADOPTION_WINDOW_DAYS} days')
            as explicit_adopted_copy_count,
          (select count(*) from copy_outcomes
            where cohort_at <= %(as_of)s
              - interval '{COMMITTED_USE_WINDOW_DAYS} days')
            as mature_committed_copy_count,
          (select count(*) from copy_outcomes
            where cohort_at <= %(as_of)s
              - interval '{COMMITTED_USE_WINDOW_DAYS} days'
              and committed_at <= cohort_at
                + interval '{COMMITTED_USE_WINDOW_DAYS} days')
            as committed_use_copy_count,
          (select count(*) from copy_outcomes
            where cohort_at <= %(as_of)s
              - interval '{COMMITTED_USE_WINDOW_DAYS} days'
              and published_at <= cohort_at
                + interval '{COMMITTED_USE_WINDOW_DAYS} days')
            as published_copy_count
        """

    @classmethod
    def _validate_measurement(cls, measurement: RetrievalMeasurement) -> None:
        if cls._required_text(measurement.tenant_id, "tenant_id") != measurement.tenant_id:
            raise ValueError("tenant_id must be normalized")
        for field, value in (
            ("actor_key", measurement.actor_key),
            ("run_key", measurement.run_key),
            ("turn_key", measurement.turn_key),
            ("tool_call_key", measurement.tool_call_key),
        ):
            if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
                raise ValueError(f"{field} must be a SHA-256 digest")
        if measurement.thread_key is not None and (
            not isinstance(measurement.thread_key, str)
            or not _DIGEST_RE.fullmatch(measurement.thread_key)
        ):
            raise ValueError("thread_key must be a SHA-256 digest")
        if measurement.outcome not in RETRIEVAL_OUTCOMES:
            raise ValueError("invalid retrieval outcome")
        if measurement.outcome == "error":
            if measurement.retrieval_mode is not None:
                raise ValueError("error measurement cannot have a retrieval mode")
            if (
                measurement.engine_count
                or measurement.degraded_engine_count
                or measurement.exposures
            ):
                raise ValueError("error measurement must contain only fixed outcome fields")
        elif measurement.retrieval_mode not in RETRIEVAL_MODES:
            raise ValueError("successful measurement requires a valid retrieval_mode")
        for field, value in (
            ("engine_count", measurement.engine_count),
            ("degraded_engine_count", measurement.degraded_engine_count),
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value <= 3
            ):
                raise ValueError(f"{field} must be between 0 and 3")
        if (
            not isinstance(measurement.latency_ms, int)
            or isinstance(measurement.latency_ms, bool)
            or measurement.latency_ms < 0
        ):
            raise ValueError("latency_ms must be a non-negative integer")
        if (
            not isinstance(measurement.observed_at, datetime)
            or measurement.observed_at.tzinfo is None
            or measurement.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must include a timezone")
        if measurement.observed_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("observed_at cannot be in the future")
        seen: set[str] = set()
        for exposure in measurement.exposures:
            if (
                not _DIGEST_RE.fullmatch(exposure.evidence_key)
                or exposure.evidence_key in seen
            ):
                raise ValueError("invalid or duplicate evidence fingerprint")
            seen.add(exposure.evidence_key)
            if not isinstance(exposure.rank, int) or exposure.rank <= 0:
                raise ValueError("exposure rank must be positive")
            for field in ("score", "relevance", "quality", "freshness", "performance"):
                value = getattr(exposure, field)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0 <= value <= 1
                ):
                    raise ValueError(f"exposure {field} must be between 0 and 1")
            if not (
                exposure.recalled_by_semantic
                or exposure.recalled_by_keyword
                or exposure.recalled_by_graph
            ):
                raise ValueError("exposure must have a retrieval source")

    @staticmethod
    def actor_key(tenant_id: str, actor_open_id: str) -> str:
        tenant_id = RetrievalMetricsRepository._required_text(tenant_id, "tenant_id")
        actor_open_id = RetrievalMetricsRepository._required_text(
            actor_open_id, "actor_open_id"
        )
        return hashlib.sha256(
            f"{tenant_id}:{actor_open_id}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _required_text(value: str, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
        return value.strip()

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return None if value is None else int(value)

    @staticmethod
    def _validate_bounds(
        *, since: datetime | None, until: datetime | None, as_of: datetime
    ) -> None:
        for field, value in (("since", since), ("until", until), ("as_of", as_of)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{field} must include a timezone")
        if since is not None and until is not None and since >= until:
            raise ValueError("since must be earlier than until")
        if until is not None and until > as_of:
            raise ValueError("until cannot be later than as_of")


__all__ = [
    "COMMITTED_USE_WINDOW_DAYS",
    "DEFAULT_MIN_SAMPLE_SIZE",
    "EXPLICIT_ADOPTION_WINDOW_DAYS",
    "RecordedRetrieval",
    "RetrievalExposure",
    "RetrievalMeasurement",
    "RetrievalMetricsRepository",
    "RetrievalOutcomeMetrics",
    "exact_evidence_key",
    "retrieval_payload_key",
]
