from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from data_foundation.db import connect
from data_foundation.embedding_service import EmbeddingIndexProfile, EmbeddingIndexService
from data_foundation.errors import classify_error
from data_foundation.outbox_repository import OutboxRepository
from data_foundation.outbox_worker import process_outbox_batch
from data_foundation.config import runtime_embedding_snapshot
from data_foundation.processors.embedding import embedding_config_from_snapshot
from data_foundation.processors.registry import default_processor_registry
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.source_repository import SourceRepository
from data_foundation.sources.base import SourceContext, SourceLease
from data_foundation.sources.registry import default_source_registry
from data_foundation.repositories.telemetry import TelemetryRepository


@dataclass(frozen=True)
class SchedulerConfig:
    component: str = "scheduler"
    instance_id: str = "scheduler"
    deployment_id: str = "local"
    config_version: str | None = None
    tenant_limit: int = 20
    outbox_batch_size: int = 20
    # 租约 TTL 必须 > 单任务硬超时(source/outbox 均 120s),否则一个 60–120s 的慢同步在
    # loader 跑完后 assert_owned→renew 时,60s 租约早已过期 → SOURCE_LEASE_LOST、刚拉的数据
    # 全扔、该区间同步按构造必败。取 180s(1.5× 超时)留足余量:慢任务跑完仍持有租约可续期,
    # 真正卡死(>180s)的才让租约过期、由 recover_expired/recover_stale_runs 回收重试。
    lease_seconds: int = 180
    stale_run_seconds: int = 3600
    retention_days: int = 90
    retention_batch_size: int = 100
    chunker_version: str = "v1"
    # 单个 source 同步 / 单批 outbox 处理的硬超时:防某租户飞书 HTTP 挂起冻结整轮 cycle。
    # 超时后该租户记 failed,租约自然过期由 recover_expired/recover_stale_runs 回收,循环继续。
    # 不变量:lease_seconds 必须 > 这两个 timeout(见上),保证慢任务不会中途丢租约。
    source_timeout_seconds: float = 120.0
    outbox_timeout_seconds: float = 120.0


@dataclass(frozen=True)
class CycleStats:
    tenants_visited: int = 0
    sources_processed: int = 0
    outbox_processed: int = 0
    recovered_sources: int = 0
    recovered_outbox: int = 0
    retention_deleted: int = 0
    failed: int = 0


@dataclass(frozen=True)
class EmbeddingRuntime:
    embedding_service: EmbeddingIndexService | None
    outbox_registry: object
    config_version: str | None


class _SourceLease(SourceLease):
    def __init__(self, source_repo, *, source_id: str, tenant_id: str, lease_owner: str, lease_seconds: int):
        self.source_repo = source_repo
        self.source_id = source_id
        self.tenant_id = tenant_id
        self.lease_owner = lease_owner
        self.lease_seconds = lease_seconds

    async def assert_owned(self) -> None:
        if not self.source_repo.renew_source(
            self.source_id,
            tenant_id=self.tenant_id,
            lease_owner=self.lease_owner,
            lease_seconds=self.lease_seconds,
        ):
            raise RuntimeError("SOURCE_LEASE_LOST")


class Scheduler:
    def __init__(
        self,
        *,
        telemetry,
        source_repo,
        outbox_repo,
        embedding_service,
        source_registry,
        outbox_registry,
        embedding_runtime_factory=None,
        process_outbox_batch=process_outbox_batch,
        config: SchedulerConfig | None = None,
        conn=None,
    ):
        self.telemetry = telemetry
        self.source_repo = source_repo
        self.outbox_repo = outbox_repo
        self.embedding_service = embedding_service
        self.source_registry = source_registry
        self.outbox_registry = outbox_registry
        self.embedding_runtime_factory = embedding_runtime_factory
        self.process_outbox_batch = process_outbox_batch
        self.config = config or SchedulerConfig()
        self._cycle_config_version = self.config.config_version
        # 关停协作:supervisor 在 stop 时调 request_stop() 置位,run_cycle 的租户循环
        # 每轮检查、及时收尾。_conn 由 build_scheduler 传入,stop() 时关闭(消除连接泄漏)。
        self._conn = conn
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        """协作式停止信号:run_cycle 的租户循环检查到即提前收尾(不再磨完所有租户)。"""
        self._stop_event.set()

    def stop(self) -> None:
        """supervisor 在确认 cycle 线程已退出后调用:登记实例下线 + 关闭独占连接。

        必须在 worker 线程真正结束之后调用(supervisor 用 executor.shutdown(wait=True)
        保证),否则与仍在用同一 conn 的孤儿线程产生 psycopg 连接竞态。
        """
        try:
            self.telemetry.stop_instance(
                component=self.config.component,
                instance_id=self.config.instance_id,
                deployment_id=self.config.deployment_id,
            )
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    async def run_cycle(self) -> CycleStats:
        self._refresh_embedding_runtime()
        self.telemetry.register_instance(
            component=self.config.component,
            instance_id=self.config.instance_id,
            deployment_id=self.config.deployment_id,
            config_version=self._cycle_config_version,
        )
        self.telemetry.heartbeat(
            component=self.config.component,
            instance_id=self.config.instance_id,
            deployment_id=self.config.deployment_id,
        )
        execution_id = self.telemetry.start_execution(
            component=self.config.component,
            instance_id=self.config.instance_id,
            tenant_id=None,
            operation="cycle",
            config_version=self._cycle_config_version,
        )
        try:
            stats = await self._run_cycle_body()
        except Exception as exc:
            self.telemetry.finish_execution(
                execution_id,
                tenant_id=None,
                status="failed",
                failed_count=1,
                error=exc,
            )
            raise

        processed = stats.sources_processed + stats.outbox_processed
        self.telemetry.finish_execution(
            execution_id,
            tenant_id=None,
            status="succeeded" if stats.failed == 0 else "failed",
            processed_count=processed,
            succeeded_count=max(0, processed - stats.failed),
            failed_count=stats.failed,
        )
        return stats

    def _refresh_embedding_runtime(self) -> None:
        if self.embedding_runtime_factory is None:
            return
        runtime = self.embedding_runtime_factory()
        self.embedding_service = runtime.embedding_service
        self.outbox_registry = runtime.outbox_registry
        self._cycle_config_version = runtime.config_version

    async def _run_cycle_body(self) -> CycleStats:
        recovered_sources = self.source_repo.recover_stale_runs(
            older_than_seconds=self.config.stale_run_seconds,
            limit=self.config.tenant_limit,
        )
        recovered_outbox = self.outbox_repo.recover_expired(limit=self.config.outbox_batch_size)
        tenants = self._discover_work_tenants()

        sources_processed = 0
        outbox_processed = 0
        failed = 0
        lease_owner = f"{self.config.instance_id}:{uuid4()}"
        for tenant_id in tenants:
            if self._stop_event.is_set():
                # 收到停止信号:及时收尾,不再磨完剩余租户(本轮 retention 下轮补偿)。
                break
            source_result = await self._process_one_source(tenant_id, lease_owner=lease_owner)
            sources_processed += source_result["processed"]
            failed += source_result["failed"]
            failed += self._prepare_processors(tenant_id)
            outbox_result = await self._process_outbox(tenant_id, lease_owner=lease_owner)
            outbox_processed += outbox_result["processed"]
            failed += outbox_result["failed"]

        retention_deleted = self.telemetry.aggregate_and_delete_old_errors(
            older_than=datetime.now(timezone.utc) - timedelta(days=self.config.retention_days),
            limit=self.config.retention_batch_size,
        )
        return CycleStats(
            tenants_visited=len(tenants),
            sources_processed=sources_processed,
            outbox_processed=outbox_processed,
            recovered_sources=recovered_sources,
            recovered_outbox=recovered_outbox,
            retention_deleted=retention_deleted,
            failed=failed,
        )

    def _discover_work_tenants(self) -> list[str]:
        limit = max(1, self.config.tenant_limit)
        source = self.source_repo.discover_due_tenants(limit=limit)
        embedding = (
            self.embedding_service.discover_reconcile_tenants(limit=limit)
            if self.embedding_service is not None
            else []
        )
        ready = self.outbox_repo.discover_ready_tenants(limit=limit)
        # 发现有 blocked 任务且对应 processor 现已 active 的租户,避免 processor 从 disabled
        # 转 active 后历史 blocked 任务无人 unblock 的死锁(如 meili/graph 引擎启用)。
        active_topics = [
            topic for topic in self.outbox_registry.topics
            if self.outbox_registry.state_for(topic).status == "active"
        ]
        blocked = self.outbox_repo.discover_blocked_tenants(topics=active_topics, limit=limit)
        source_set = set(source)
        non_source = _unique(
            [tenant_id for tenant_id in embedding + ready + blocked if tenant_id not in source_set]
        )
        source_budget = limit if limit == 1 or not non_source else limit - 1
        return _unique(source[:source_budget] + non_source + source[source_budget:])[:limit]

    def _prepare_processors(self, tenant_id: str) -> int:
        failed = 0
        for topic in self.outbox_registry.topics:
            state = self.outbox_registry.state_for(topic)
            if state.status != "active":
                continue
            # 整个 topic 的准备(reconcile + unblock)包在一个 try 里:任一步抛 DB 异常
            # 只让该 topic 记 failed,不冒泡出 _run_cycle_body 中止整轮(原 unblock_available
            # 在 except 之外,出错会跳过剩余租户 + retention)。
            try:
                if topic == "embedding_generate" and self.embedding_service is not None:
                    self.embedding_service.reconcile_tenant(tenant_id)
                self.outbox_repo.unblock_available(tenant_id=tenant_id, topic=topic)
            except Exception:
                failed += 1
        return failed

    async def _process_one_source(self, tenant_id: str, *, lease_owner: str) -> dict[str, int]:
        source = self.source_repo.lease_due_source(
            tenant_id=tenant_id,
            lease_owner=lease_owner,
            lease_seconds=self.config.lease_seconds,
        )
        if source is None:
            return {"processed": 0, "failed": 0}
        execution_id = self.telemetry.start_execution(
            component=self.config.component,
            instance_id=self.config.instance_id,
            tenant_id=tenant_id,
            operation=f"source:{source.source_type}",
            config_version=self._cycle_config_version,
        )
        run_id = self.source_repo.start_run(
            source.id,
            tenant_id=tenant_id,
            instance_id=self.config.instance_id,
            execution_id=execution_id,
        )
        try:
            processor = self.source_registry.processor_for(source.source_type)
            if processor is None:
                raise RuntimeError(f"Source processor disabled: {source.source_type}")
            public_source, secrets = self.source_repo.get_source_with_secrets(
                tenant_id=tenant_id,
                source_id=source.id,
            )
            result = await asyncio.wait_for(
                processor.sync(
                    SourceContext(source=public_source, secrets=secrets, actor_open_id=self.config.instance_id, as_bot=True),
                    _SourceLease(
                        self.source_repo,
                        source_id=source.id,
                        tenant_id=tenant_id,
                        lease_owner=lease_owner,
                        lease_seconds=self.config.lease_seconds,
                    ),
                ),
                timeout=self.config.source_timeout_seconds,
            )
            self.source_repo.finish_run(
                run_id,
                tenant_id=tenant_id,
                status=result.status,
                cursor_after=result.cursor,
                read_count=result.read_count,
                created_count=result.created_count,
                updated_count=result.updated_count,
                skipped_count=result.skipped_count,
                failed_count=result.failed_count,
                error_code=None,
                error_summary="\n".join(result.errors) if result.errors else None,
            )
            self.source_repo.finish_source(
                source.id,
                tenant_id=tenant_id,
                lease_owner=lease_owner,
                cursor=result.cursor,
                next_run_after_seconds=source.schedule_seconds,
            )
            self.telemetry.finish_execution(
                execution_id,
                tenant_id=tenant_id,
                status="succeeded" if result.status in {"succeeded", "partial"} else "failed",
                processed_count=result.read_count,
                succeeded_count=result.created_count + result.updated_count,
                failed_count=result.failed_count,
                error_summary="\n".join(result.errors) if result.errors else None,
            )
            return {"processed": 1, "failed": 0 if result.status in {"succeeded", "partial"} else 1}
        except Exception as exc:
            classification = classify_error(exc, component=self.config.component, operation=f"source:{source.source_type}")
            self.source_repo.finish_run(
                run_id,
                tenant_id=tenant_id,
                status="failed",
                cursor_after=None,
                read_count=0,
                created_count=0,
                updated_count=0,
                skipped_count=0,
                failed_count=1,
                error_code=classification.error_code,
                error_summary=classification.error_summary,
            )
            self.telemetry.finish_execution(
                execution_id,
                tenant_id=tenant_id,
                status="failed",
                failed_count=1,
                error_code=classification.error_code,
                error_summary=classification.error_summary,
            )
            return {"processed": 0, "failed": 1}

    async def _process_outbox(self, tenant_id: str, *, lease_owner: str) -> dict[str, int]:
        execution_id = self.telemetry.start_execution(
            component=self.config.component,
            instance_id=self.config.instance_id,
            tenant_id=tenant_id,
            operation="outbox",
            config_version=self._cycle_config_version,
        )
        try:
            stats = await asyncio.wait_for(
                self.process_outbox_batch(
                    self.outbox_repo,
                    tenant_id=tenant_id,
                    registry=self.outbox_registry,
                    batch_size=self.config.outbox_batch_size,
                    lease_owner=lease_owner,
                    lease_seconds=self.config.lease_seconds,
                ),
                timeout=self.config.outbox_timeout_seconds,
            )
            processed = int(stats.get("processed", 0))
            failed = int(stats.get("failed", 0))
            succeeded = int(stats.get("succeeded", 0))
            self.telemetry.finish_execution(
                execution_id,
                tenant_id=tenant_id,
                status="succeeded" if failed == 0 else "failed",
                processed_count=processed,
                succeeded_count=succeeded,
                failed_count=failed,
                error_summary="\n".join(str(error) for error in stats.get("errors", [])) or None,
            )
            return {"processed": processed, "failed": 1 if failed else 0}
        except Exception as exc:
            classification = classify_error(exc, component=self.config.component, operation="outbox")
            self.telemetry.finish_execution(
                execution_id,
                tenant_id=tenant_id,
                status="failed",
                failed_count=1,
                error_code=classification.error_code,
                error_summary=classification.error_summary,
            )
            return {"processed": 0, "failed": 1}


def _unique(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _build_embedding_runtime(conn, *, config: SchedulerConfig) -> EmbeddingRuntime:
    snapshot = runtime_embedding_snapshot()
    embedding_config = embedding_config_from_snapshot(snapshot)
    embedding_service = None
    if embedding_config is not None and embedding_config.state == "enabled":
        embedding_service = EmbeddingIndexService(
            conn,
            profile=EmbeddingIndexProfile(
                embedding_model=embedding_config.model,
                config_version=embedding_config.config_version,
                chunker_version=config.chunker_version,
            ),
        )
    return EmbeddingRuntime(
        embedding_service=embedding_service,
        outbox_registry=default_processor_registry(
            conn,
            embedding_config=embedding_config,
            # preference_synthesize runs in a worker thread and must own a connection
            # separate from this scheduler/outbox lease connection.
            preference_connection_factory=connect,
        ),
        config_version=snapshot.version,
    )


def build_scheduler(config: SchedulerConfig | None = None) -> Scheduler:
    config = config or SchedulerConfig()
    conn = connect()
    resource_repo = ResourceRepository(conn)
    runtime_factory = lambda: _build_embedding_runtime(conn, config=config)
    initial_runtime = runtime_factory()
    return Scheduler(
        telemetry=TelemetryRepository(conn),
        source_repo=SourceRepository(conn),
        outbox_repo=OutboxRepository(conn),
        embedding_service=initial_runtime.embedding_service,
        source_registry=default_source_registry(resource_repo),
        outbox_registry=initial_runtime.outbox_registry,
        embedding_runtime_factory=runtime_factory,
        process_outbox_batch=process_outbox_batch,
        config=config,
        conn=conn,
    )
