from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from config_center import latest_config_snapshot
from data_foundation.db import connect
from data_foundation.embedding_service import EmbeddingIndexProfile, EmbeddingIndexService
from data_foundation.errors import classify_error
from data_foundation.outbox_repository import OutboxRepository
from data_foundation.outbox_worker import process_outbox_batch
from data_foundation.config import runtime_embedding_snapshot
from data_foundation.processors.embedding import embedding_config_from_snapshot
from data_foundation.processors.registry import default_processor_registry
from data_foundation.repository import ResourceRepository
from data_foundation.source_repository import SourceRepository
from data_foundation.sources.base import SourceContext, SourceLease
from data_foundation.sources.registry import default_source_registry
from data_foundation.telemetry_repository import TelemetryRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchedulerConfig:
    component: str = "scheduler"
    instance_id: str = "scheduler"
    deployment_id: str = "local"
    config_version: str | None = None
    tenant_limit: int = 20
    outbox_batch_size: int = 20
    lease_seconds: int = 60
    stale_run_seconds: int = 3600
    retention_days: int = 90
    retention_batch_size: int = 100
    chunker_version: str = "v1"


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
        model_registry=None,
        model_snapshot_provider=latest_config_snapshot,
        config: SchedulerConfig | None = None,
    ):
        self.telemetry = telemetry
        self.source_repo = source_repo
        self.outbox_repo = outbox_repo
        self.embedding_service = embedding_service
        self.source_registry = source_registry
        self.outbox_registry = outbox_registry
        self.embedding_runtime_factory = embedding_runtime_factory
        self.process_outbox_batch = process_outbox_batch
        # 模型池热重载:与 embedding 刷新对称。registry 为 agent.py 的进程内单例
        # (N_WORKERS=1,graph 与 scheduler 同进程同内存)。provider 默认读 config-center
        # 最新快照,二者均缺省时本机制为 no-op(纯 env 部署/测试无需热载)。
        self.model_registry = model_registry
        self.model_snapshot_provider = model_snapshot_provider
        self.config = config or SchedulerConfig()
        self._cycle_config_version = self.config.config_version

    async def run_cycle(self) -> CycleStats:
        self._refresh_embedding_runtime()
        self._refresh_model_pool()
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

    def _refresh_model_pool(self) -> None:
        """与 embedding 刷新对称:每 cycle 比对 config-center 版本,变化则重建模型池。

        - 无 registry 或无 provider:本机制未启用(测试/纯 env 部署的合法配置),返回。
          注:server 进程内必有 registry(http_app 强制注入,拿不到会在启动时炸),
          故此分支不会在生产命中,不是"拿不到就关掉"的兜底。
        - 快照为 None(配置中心未配/history 空):配置中心确无内容,保留启动池。
        - 版本未变:跳过,避免无谓的网关探测与模型实例重建。
        - reload 失败:属运行时瞬时错误(网关探测不通/新配置 verify 失败),与 source
          同步、outbox 处理正交,不应拖垮整轮 cycle。reload_from_config 内部已 record_error
          (经 runtime-facts 对 admin 可见),旧池继续服务,下一 cycle 自动重试。
        """
        if self.model_registry is None or self.model_snapshot_provider is None:
            return
        snapshot = self.model_snapshot_provider()
        if snapshot is None:
            return
        if snapshot.version == self.model_registry.status().get("version"):
            return
        try:
            self.model_registry.reload_from_config(snapshot)
        except Exception:
            logger.warning("model_pool_reload_failed version=%s", snapshot.version)

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
            if state.status == "active":
                if topic == "embedding_generate":
                    try:
                        if self.embedding_service is not None:
                            self.embedding_service.reconcile_tenant(tenant_id)
                    except Exception:
                        failed += 1
                self.outbox_repo.unblock_available(tenant_id=tenant_id, topic=topic)
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
            result = await processor.sync(
                SourceContext(source=public_source, secrets=secrets, actor_open_id=self.config.instance_id),
                _SourceLease(
                    self.source_repo,
                    source_id=source.id,
                    tenant_id=tenant_id,
                    lease_owner=lease_owner,
                    lease_seconds=self.config.lease_seconds,
                ),
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
            stats = await self.process_outbox_batch(
                self.outbox_repo,
                tenant_id=tenant_id,
                registry=self.outbox_registry,
                batch_size=self.config.outbox_batch_size,
                lease_owner=lease_owner,
                lease_seconds=self.config.lease_seconds,
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
        outbox_registry=default_processor_registry(conn, embedding_config=embedding_config),
        config_version=snapshot.version,
    )


def build_scheduler(config: SchedulerConfig | None = None, *, model_registry=None) -> Scheduler:
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
        model_registry=model_registry,
        config=config,
    )
