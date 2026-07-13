from __future__ import annotations

import hashlib
import json
from typing import Any


def enqueue_preference_synthesis(
    cursor,
    *,
    tenant_id: str,
    actor_open_id: str,
    trigger_key: str,
    trigger_payload: dict[str, Any] | None = None,
) -> int | None:
    """Record one immutable synthesis trigger and debounce it to an actor job.

    Replaying the same knowledge/ACL fact is a no-op.  A genuinely new fact advances
    the actor revision, revokes an older lease, and leaves exactly one pending outbox
    row carrying the newest requested revision.
    """
    actor = actor_open_id.strip() if isinstance(actor_open_id, str) else ""
    key = trigger_key.strip() if isinstance(trigger_key, str) else ""
    if not actor or not key:
        return None
    payload = dict(trigger_payload or {})
    inserted = cursor.execute(
        """
        insert into preference_synthesis_events (
          tenant_id, owner_open_id, trigger_key, trigger_payload
        ) values (%s, %s, %s, %s::jsonb)
        on conflict (tenant_id, owner_open_id, trigger_key) do nothing
        returning trigger_key
        """,
        (
            tenant_id,
            actor,
            key,
            json.dumps(payload, sort_keys=True, ensure_ascii=False),
        ),
    ).fetchone()
    if inserted is None:
        return None
    state = cursor.execute(
        """
        insert into preference_synthesis_states (
          tenant_id, owner_open_id, requested_revision, completed_revision
        ) values (%s, %s, 1, 0)
        on conflict (tenant_id, owner_open_id) do update
        set requested_revision = preference_synthesis_states.requested_revision + 1,
            updated_at = now()
        returning requested_revision
        """,
        (tenant_id, actor),
    ).fetchone()
    revision = int(state["requested_revision"])
    dedupe_key = hashlib.sha256(
        json.dumps(
            [tenant_id, "preference_synthesize", actor],
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    outbox_payload = {
        "actor_open_id": actor,
        "requested_revision": revision,
        "trigger": payload,
    }
    cursor.execute(
        """
        insert into resource_outbox (
          tenant_id, topic, dedupe_key, payload, next_attempt_at
        ) values (
          %s, 'preference_synthesize', %s, %s::jsonb,
          now() + interval '1 second'
        )
        on conflict (tenant_id, dedupe_key) do update
        set topic = excluded.topic,
            payload = excluded.payload,
            status = 'pending',
            attempts = 0,
            next_attempt_at = now() + interval '1 second',
            lease_owner = null,
            lease_expires_at = null,
            error_code = null,
            error_summary = null,
            dead_at = null,
            updated_at = now()
        """,
        (
            tenant_id,
            dedupe_key,
            json.dumps(outbox_payload, sort_keys=True, ensure_ascii=False),
        ),
    )
    return revision


__all__ = ["enqueue_preference_synthesis"]
