from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from data_foundation.models import SourceSecrets, SyncSource


@dataclass(frozen=True)
class SourceContext:
    source: SyncSource
    secrets: SourceSecrets
    actor_open_id: str
    # 身份意图:后台无人值守自动同步走 bot(应用身份,自刷新);
    # 前端交互触发的手动同步走 actor 的 UAT(用户身份)。默认 False(UAT)。
    as_bot: bool = False


@dataclass(frozen=True)
class SourceSyncResult:
    status: str
    read_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    errors: list[str]
    cursor: dict


class SourceLease(Protocol):
    async def assert_owned(self) -> None: ...


class SourceProcessor(Protocol):
    source_type: str

    async def sync(self, context: SourceContext, lease: SourceLease) -> SourceSyncResult: ...

