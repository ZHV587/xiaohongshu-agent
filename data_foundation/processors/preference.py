from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from psycopg import Connection

from data_foundation import db
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.preference_learning import PreferenceLearningService
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult
from data_foundation.repositories.resource import ResourceRepository


class PreferenceSynthesizeProcessor:
    """Run actor-scoped O(N) pattern synthesis outside knowledge enrichment."""

    topic = "preference_synthesize"

    def __init__(
        self,
        conn: Connection,
        *,
        service: PreferenceLearningService | None = None,
        connection_factory: Callable[[], Connection] | None = None,
    ) -> None:
        # The scheduler's connection is also used by OutboxRepository for lease
        # heartbeats.  A psycopg connection has one transaction shared by all threads,
        # so preference synthesis must never run on that connection.
        self._injected_service = service
        self._connection_factory = connection_factory or db.connect

    def _call_service(self, method: str, **kwargs: Any) -> Any:
        if self._injected_service is not None:
            return getattr(self._injected_service, method)(**kwargs)
        connection = self._connection_factory()
        try:
            service = PreferenceLearningService(ResourceRepository(connection))
            return getattr(service, method)(**kwargs)
        finally:
            connection.close()

    def state(self) -> ProcessorState:
        return ProcessorState(
            topic=self.topic,
            status="active",
            config_version="preference-synthesize-v1",
            reason_code=None,
        )

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult:
        actor_open_id = str(item.payload.get("actor_open_id") or "").strip()
        if not actor_open_id:
            raise PermanentProcessingError(
                "Preference synthesis payload missing actor_open_id"
            )
        requested_revision = item.payload.get("requested_revision")
        if (
            not isinstance(requested_revision, int)
            or isinstance(requested_revision, bool)
            or requested_revision <= 0
        ):
            raise PermanentProcessingError(
                "Preference synthesis payload missing requested_revision"
            )
        await lease.assert_owned()
        work = asyncio.create_task(
            asyncio.to_thread(
                self._call_service,
                "synthesize_patterns",
                tenant_id=item.tenant_id,
                actor_open_id=actor_open_id,
            )
        )
        heartbeat_seconds = max(
            1.0, min(float(getattr(lease, "lease_seconds", 60)) / 3.0, 20.0)
        )
        try:
            while not work.done():
                done, _pending = await asyncio.wait({work}, timeout=heartbeat_seconds)
                if done:
                    break
                await lease.assert_owned()
        except BaseException:
            # asyncio cannot cancel a function already running in a worker thread.
            # Always retrieve/finish it before returning LEASE_LOST or cancellation;
            # otherwise it becomes an unowned writer racing the replacement job.
            try:
                await asyncio.shield(work)
            except BaseException:
                pass
            raise
        saved = await work
        await lease.assert_owned()
        completed = await asyncio.to_thread(
            self._call_service,
            "mark_synthesis_completed",
            tenant_id=item.tenant_id,
            actor_open_id=actor_open_id,
            requested_revision=requested_revision,
        )
        if not completed:
            raise RuntimeError("PREFERENCE_SYNTHESIS_REVISION_STALE")
        return ProcessResult(status="succeeded", processed_count=len(saved))


__all__ = ["PreferenceSynthesizeProcessor"]
