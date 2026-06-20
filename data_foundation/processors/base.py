from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol

from data_foundation.models import OutboxItem, ProcessorState


@dataclass(frozen=True)
class ProcessResult:
    status: Literal["succeeded", "superseded"]
    processed_count: int = 1


@dataclass(frozen=True)
class ItemProcessResult:
    status: str
    error_code: str | None = None
    error_summary: str | None = None


class LeaseGuard:
    def __init__(
        self,
        repo,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        lease_seconds: int,
    ):
        self.repo = repo
        self.item_id = item_id
        self.tenant_id = tenant_id
        self.lease_owner = lease_owner
        self.lease_seconds = lease_seconds

    async def assert_owned(self) -> None:
        owned = await asyncio.to_thread(
            self.repo.renew,
            item_id=self.item_id,
            tenant_id=self.tenant_id,
            lease_owner=self.lease_owner,
            lease_seconds=self.lease_seconds,
        )
        if not owned:
            raise RuntimeError("LEASE_LOST")


class Processor(Protocol):
    topic: str

    def state(self) -> ProcessorState: ...

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult: ...
