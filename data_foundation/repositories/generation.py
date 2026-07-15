from __future__ import annotations

import json
from typing import Any, Mapping

from psycopg.rows import dict_row

from data_foundation.generation_provenance import run_key
from data_foundation.repositories.base import BaseRepository
from data_foundation.writing_context import WritingContext


class GenerationRepository(BaseRepository):
    def record_generation(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        variants: list[dict[str, Any]],
        run_id: str | None,
        turn_id: str | None,
        thread_id: str | None,
        task_type: str,
        request_digest: str,
        prompt_contract_version: str,
        model: Mapping[str, Any],
        knowledge_grounding: Mapping[str, Any],
        profile: Mapping[str, Any] | None,
        user_skill: Mapping[str, Any] | None,
        writing_context: WritingContext,
    ) -> str:
        if task_type not in {"copywriting", "imitation", "revision", "other"}:
            raise ValueError("unsupported generation task_type")
        if not variants:
            raise ValueError("generation variants are required")
        identity = {
            "tenant_id": tenant_id,
            "owner_open_id": actor_open_id,
            "run_id": run_id,
            "turn_id": turn_id,
            "resource_id": resource_id,
            "versions": [int(item["resource_version"]) for item in variants],
        }
        profile_id = profile.get("resource_id") if isinstance(profile, Mapping) else None
        profile_version = profile.get("resource_version") if isinstance(profile, Mapping) else None
        skill_id = user_skill.get("skill_id") if isinstance(user_skill, Mapping) else None
        skill_version_id = user_skill.get("version_id") if isinstance(user_skill, Mapping) else None
        with self.connection_context() as connection:
            row = connection.execute(
                """
                insert into generation_runs (
                  tenant_id, owner_open_id, run_key, run_id, turn_id, thread_id,
                  task_type, request_digest, prompt_contract_version,
                  model_provider, model_id, gateway_name, knowledge_grounding,
                  profile_resource_id, profile_resource_version,
                  user_skill_id, user_skill_version_id, account_id, niche
                ) values (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s
                )
                on conflict (tenant_id, owner_open_id, run_key) do update
                set run_key = excluded.run_key
                returning id::text
                """,
                (
                    tenant_id,
                    actor_open_id,
                    run_key(identity),
                    run_id,
                    turn_id,
                    thread_id,
                    task_type,
                    request_digest,
                    prompt_contract_version,
                    model.get("provider"),
                    model.get("model_id"),
                    model.get("gateway_name"),
                    json.dumps(dict(knowledge_grounding), ensure_ascii=False, sort_keys=True),
                    profile_id,
                    profile_version,
                    skill_id,
                    skill_version_id,
                    writing_context.account_id,
                    writing_context.niche,
                ),
            ).fetchone()
            generation_run_id = str(row["id"])
            for ordinal, variant in enumerate(variants, start=1):
                connection.execute(
                    """
                    insert into generation_variants (
                      tenant_id, generation_run_id, resource_id, resource_version,
                      label, ordinal
                    ) values (%s, %s, %s, %s, %s, %s)
                    on conflict (
                      tenant_id, generation_run_id, resource_id, resource_version
                    ) do nothing
                    """,
                    (
                        tenant_id,
                        generation_run_id,
                        resource_id,
                        int(variant["resource_version"]),
                        str(variant.get("label") or f"V{ordinal}"),
                        ordinal,
                    ),
                )
        return generation_run_id

    def record_selection(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        selection_event_id: str,
    ) -> list[dict[str, Any]]:
        """把一次选中机械展开成 chosen > 每个已展示未选版本的配对事实。"""

        with self.connection_context() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                chosen = cursor.execute(
                    """
                    select variant.generation_run_id::text, variant.ordinal
                    from generation_variants variant
                    join generation_runs run
                      on run.id = variant.generation_run_id
                     and run.tenant_id = variant.tenant_id
                    where variant.tenant_id = %s
                      and run.owner_open_id = %s
                      and variant.resource_id = %s
                      and variant.resource_version = %s
                    order by run.presentation_sequence desc
                    limit 1
                    """,
                    (tenant_id, actor_open_id, resource_id, resource_version),
                ).fetchone()
                comparisons: list[dict[str, Any]] = []
                if chosen is not None:
                    rejected = cursor.execute(
                        """
                        select resource_id::text, resource_version, ordinal
                        from generation_variants
                        where tenant_id = %s and generation_run_id = %s
                          and not (resource_id = %s and resource_version = %s)
                        order by ordinal
                        """,
                        (
                            tenant_id,
                            chosen["generation_run_id"],
                            resource_id,
                            resource_version,
                        ),
                    ).fetchall()
                    connection.execute(
                        """
                        update generation_variants set selected_at = now()
                        where tenant_id = %s and generation_run_id = %s
                          and resource_id = %s and resource_version = %s
                        """,
                        (tenant_id, chosen["generation_run_id"], resource_id, resource_version),
                    )
                    for item in rejected:
                        inserted = connection.execute(
                            """
                            insert into generation_pairwise_preferences (
                              tenant_id, owner_open_id, generation_run_id,
                              chosen_resource_id, chosen_resource_version,
                              rejected_resource_id, rejected_resource_version,
                              chosen_ordinal, rejected_ordinal, selection_event_id
                            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            on conflict do nothing
                            returning rejected_resource_id::text, rejected_resource_version,
                                      chosen_ordinal, rejected_ordinal
                            """,
                            (
                                tenant_id,
                                actor_open_id,
                                chosen["generation_run_id"],
                                resource_id,
                                resource_version,
                                item["resource_id"],
                                int(item["resource_version"]),
                                int(chosen["ordinal"]),
                                int(item["ordinal"]),
                                selection_event_id,
                            ),
                        ).fetchone()
                        if inserted is not None:
                            comparisons.append(
                                {
                                    **dict(inserted),
                                    "generation_run_id": str(chosen["generation_run_id"]),
                                }
                            )
        return comparisons


__all__ = ["GenerationRepository"]
