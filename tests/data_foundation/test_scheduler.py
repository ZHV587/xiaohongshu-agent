from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from data_foundation.scheduler import Scheduler, SchedulerConfig


@dataclass
class FakeTelemetry:
    registered: list[dict] = field(default_factory=list)
    heartbeats: list[dict] = field(default_factory=list)
    starts: list[dict] = field(default_factory=list)
    finishes: list[dict] = field(default_factory=list)
    next_execution_id: int = 0

    def register_instance(self, **kwargs):
        self.registered.append(kwargs)
        return None

    def heartbeat(self, **kwargs):
        self.heartbeats.append(kwargs)
        return True

    def start_execution(self, **kwargs):
        self.starts.append(kwargs)
        self.next_execution_id += 1
        return f"exec-{self.next_execution_id}"

    def finish_execution(self, execution_id, **kwargs):
        self.finishes.append({"execution_id": execution_id, **kwargs})
        return True

    def aggregate_and_delete_old_errors(self, **kwargs):
        return 0


@dataclass
class FakeRetrievalMetrics:
    deleted: int = 0
    calls: list[dict] = field(default_factory=list)

    def delete_expired(self, **kwargs):
        self.calls.append(kwargs)
        return self.deleted


@dataclass
class FakeSourceRepo:
    tenants: list[str]
    leased: dict[str, object | None] = field(default_factory=dict)
    finished: list[dict] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)
    recovered: int = 0

    def discover_due_tenants(self, *, limit):
        return self.tenants[:limit]

    def recover_stale_runs(self, **kwargs):
        return self.recovered

    def lease_due_source(self, *, tenant_id, lease_owner, lease_seconds):
        return self.leased.get(tenant_id)

    def get_source_with_secrets(self, *, tenant_id, source_id):
        source = self.leased[tenant_id]
        return source, type("Secrets", (), {"credentials": {}})()

    def start_run(self, source_id, **kwargs):
        self.runs.append({"source_id": source_id, **kwargs})
        return f"run-{source_id}"

    def finish_run(self, run_id, **kwargs):
        self.finished.append({"run_id": run_id, **kwargs})
        return True

    def finish_source(self, source_id, **kwargs):
        self.finished.append({"source_id": source_id, **kwargs})
        return True

    def renew_source(self, source_id, **kwargs):
        return True


@dataclass
class FakeOutboxRepo:
    recovered: int = 0
    ready_tenants: list[str] = field(default_factory=list)
    blocked_tenants: list[str] = field(default_factory=list)
    unblocked: list[dict] = field(default_factory=list)

    def recover_expired(self, *, limit):
        return self.recovered

    def discover_ready_tenants(self, *, limit):
        return self.ready_tenants[:limit]

    def discover_blocked_tenants(self, *, topics, limit):
        return self.blocked_tenants[:limit]

    def unblock_available(self, *, tenant_id, topic):
        self.unblocked.append({"tenant_id": tenant_id, "topic": topic})
        return 0


@dataclass
class FakeEmbeddingService:
    calls: list[str] = field(default_factory=list)
    reconcile_tenants: list[str] = field(default_factory=list)

    def discover_reconcile_tenants(self, *, limit):
        return self.reconcile_tenants[:limit]

    def reconcile_tenant(self, tenant_id: str):
        self.calls.append(tenant_id)
        return type(
            "Result",
            (),
            {
                "embedding_index_id": f"idx-{tenant_id}",
                "enqueued": 0,
                "activated": True,
            },
        )()


@dataclass
class FakeOutboxRunner:
    calls: list[str] = field(default_factory=list)
    raise_for_tenant: str | None = None

    async def __call__(self, repo, tenant_id, **kwargs):
        self.calls.append(tenant_id)
        if tenant_id == self.raise_for_tenant:
            raise RuntimeError("token=secret")
        return {"processed": 2, "succeeded": 1, "failed": 1, "blocked": 0}


class FakeSourceProcessor:
    def __init__(self, status="succeeded"):
        self.status = status
        self.calls = []

    async def sync(self, context, lease):
        self.calls.append(context.source.id)
        await lease.assert_owned()
        return type(
            "Result",
            (),
            {
                "status": self.status,
                "read_count": 3,
                "created_count": 2,
                "updated_count": 1,
                "skipped_count": 0,
                "failed_count": 0,
                "errors": [],
                "cursor": {"last": "3"},
            },
        )()


class FakeSourceRegistry:
    def __init__(self, processor):
        self.processor = processor

    def processor_for(self, source_type):
        return self.processor


class FakeOutboxRegistry:
    def __init__(self, status="active"):
        self.topics = ["embedding_generate"]
        self.status = status

    def state_for(self, topic):
        return type("ProcessorState", (), {"status": self.status})()


@dataclass
class FakeEmbeddingRuntime:
    embedding_service: object | None
    outbox_registry: object
    config_version: str | None


def _source(source_id: str, tenant_id: str):
    return type(
        "Source",
        (),
        {
            "id": source_id,
            "tenant_id": tenant_id,
            "source_type": "feishu_base",
            "schedule_seconds": 60,
        },
    )()


@pytest.mark.asyncio
async def test_empty_cycle_records_successful_execution():
    telemetry = FakeTelemetry()
    retrieval_metrics = FakeRetrievalMetrics(deleted=3)
    scheduler = Scheduler(
        telemetry=telemetry,
        retrieval_metrics=retrieval_metrics,
        source_repo=FakeSourceRepo(tenants=[]),
        outbox_repo=FakeOutboxRepo(),
        embedding_service=None,
        source_registry=FakeSourceRegistry(None),
        outbox_registry=FakeOutboxRegistry(status="disabled"),
        process_outbox_batch=FakeOutboxRunner(),
        config=SchedulerConfig(component="scheduler", instance_id="i1", deployment_id="d1"),
    )

    stats = await scheduler.run_cycle()

    assert stats.tenants_visited == 0
    assert stats.retrieval_retention_deleted == 3
    assert len(retrieval_metrics.calls) == 1
    assert retrieval_metrics.calls[0]["limit"] == 100
    retention_age = datetime.now(UTC) - retrieval_metrics.calls[0]["older_than"]
    assert timedelta(days=89) < retention_age < timedelta(days=91)
    assert telemetry.starts == [{
        "component": "scheduler",
        "instance_id": "i1",
        "tenant_id": None,
        "operation": "cycle",
        "config_version": None,
    }]
    assert telemetry.finishes == [{
        "execution_id": "exec-1",
        "tenant_id": None,
        "status": "succeeded",
        "processed_count": 0,
        "succeeded_count": 0,
        "failed_count": 0,
    }]


@pytest.mark.asyncio
async def test_cycle_dispatches_one_batch_per_tenant_in_fair_order():
    telemetry = FakeTelemetry()
    outbox_repo = FakeOutboxRepo()
    embedding_service = FakeEmbeddingService()
    source_repo = FakeSourceRepo(
        tenants=["waiting", "busy"],
        leased={"waiting": _source("s1", "waiting"), "busy": None},
    )
    outbox_runner = FakeOutboxRunner()
    source_processor = FakeSourceProcessor()
    scheduler = Scheduler(
        telemetry=telemetry,
        retrieval_metrics=FakeRetrievalMetrics(),
        source_repo=source_repo,
        outbox_repo=outbox_repo,
        embedding_service=embedding_service,
        source_registry=FakeSourceRegistry(source_processor),
        outbox_registry=FakeOutboxRegistry(),
        process_outbox_batch=outbox_runner,
        config=SchedulerConfig(
            component="scheduler",
            instance_id="i1",
            deployment_id="d1",
            tenant_limit=10,
            outbox_batch_size=7,
        ),
    )

    stats = await scheduler.run_cycle()

    assert stats.tenants_visited == 2
    assert stats.sources_processed == 1
    assert stats.outbox_processed == 4
    assert outbox_runner.calls == ["waiting", "busy"]
    assert source_processor.calls == ["s1"]
    assert embedding_service.calls == ["waiting", "busy"]
    assert outbox_repo.unblocked == [
        {"tenant_id": "waiting", "topic": "embedding_generate"},
        {"tenant_id": "busy", "topic": "embedding_generate"},
    ]
    assert telemetry.heartbeats == [{"component": "scheduler", "instance_id": "i1", "deployment_id": "d1"}]
    assert [start["tenant_id"] for start in telemetry.starts] == [None, "waiting", "waiting", "busy"]
    cycle_finish = next(item for item in telemetry.finishes if item["execution_id"] == "exec-1")
    assert cycle_finish == {
        "execution_id": "exec-1",
        "tenant_id": None,
        "status": "failed",
        "processed_count": 5,
        "succeeded_count": 3,
        "failed_count": 2,
    }


@pytest.mark.asyncio
async def test_cycle_processes_embedding_tenant_without_sync_source():
    embedding_service = FakeEmbeddingService(reconcile_tenants=["generated"])
    scheduler = Scheduler(
        telemetry=FakeTelemetry(),
        retrieval_metrics=FakeRetrievalMetrics(),
        source_repo=FakeSourceRepo(tenants=[]),
        outbox_repo=FakeOutboxRepo(),
        embedding_service=embedding_service,
        source_registry=FakeSourceRegistry(None),
        outbox_registry=FakeOutboxRegistry(),
        process_outbox_batch=FakeOutboxRunner(),
        config=SchedulerConfig(component="scheduler", instance_id="i1", deployment_id="d1"),
    )

    stats = await scheduler.run_cycle()

    assert stats.tenants_visited == 1
    assert embedding_service.calls == ["generated"]


@pytest.mark.asyncio
async def test_cycle_reserves_non_source_slot_when_due_sources_fill_limit():
    embedding_service = FakeEmbeddingService(reconcile_tenants=["generated"])
    outbox_runner = FakeOutboxRunner()
    scheduler = Scheduler(
        telemetry=FakeTelemetry(),
        retrieval_metrics=FakeRetrievalMetrics(),
        source_repo=FakeSourceRepo(tenants=["s1", "s2", "s3"]),
        outbox_repo=FakeOutboxRepo(),
        embedding_service=embedding_service,
        source_registry=FakeSourceRegistry(None),
        outbox_registry=FakeOutboxRegistry(),
        process_outbox_batch=outbox_runner,
        config=SchedulerConfig(
            component="scheduler",
            instance_id="i1",
            deployment_id="d1",
            tenant_limit=3,
        ),
    )

    stats = await scheduler.run_cycle()

    assert stats.tenants_visited == 3
    assert outbox_runner.calls == ["s1", "s2", "generated"]


@pytest.mark.asyncio
async def test_cycle_deduplicates_tenants_across_work_categories():
    embedding_service = FakeEmbeddingService(reconcile_tenants=["shared"])
    scheduler = Scheduler(
        telemetry=FakeTelemetry(),
        retrieval_metrics=FakeRetrievalMetrics(),
        source_repo=FakeSourceRepo(tenants=["shared"]),
        outbox_repo=FakeOutboxRepo(ready_tenants=["shared"]),
        embedding_service=embedding_service,
        source_registry=FakeSourceRegistry(None),
        outbox_registry=FakeOutboxRegistry(),
        process_outbox_batch=FakeOutboxRunner(),
        config=SchedulerConfig(component="scheduler", instance_id="i1", deployment_id="d1"),
    )

    assert (await scheduler.run_cycle()).tenants_visited == 1


@pytest.mark.asyncio
async def test_cycle_records_exception_instead_of_swallowing():
    telemetry = FakeTelemetry()
    scheduler = Scheduler(
        telemetry=telemetry,
        retrieval_metrics=FakeRetrievalMetrics(),
        source_repo=FakeSourceRepo(tenants=["waiting"], leased={"waiting": None}),
        outbox_repo=FakeOutboxRepo(),
        embedding_service=FakeEmbeddingService(),
        source_registry=FakeSourceRegistry(None),
        outbox_registry=FakeOutboxRegistry(),
        process_outbox_batch=FakeOutboxRunner(raise_for_tenant="waiting"),
        config=SchedulerConfig(
            component="scheduler",
            instance_id="i1",
            deployment_id="d1",
        ),
    )

    stats = await scheduler.run_cycle()

    assert stats.failed == 1
    outbox_finish = next(item for item in telemetry.finishes if item["tenant_id"] == "waiting")
    assert outbox_finish["status"] == "failed"
    assert "secret" not in outbox_finish["error_summary"]
    assert "token=<redacted>" in outbox_finish["error_summary"]
    cycle_finish = next(item for item in telemetry.finishes if item["tenant_id"] is None)
    assert cycle_finish["status"] == "failed"


@pytest.mark.asyncio
async def test_cycle_does_not_reconcile_or_unblock_disabled_processors():
    outbox_repo = FakeOutboxRepo()
    embedding_service = FakeEmbeddingService()
    scheduler = Scheduler(
        telemetry=FakeTelemetry(),
        retrieval_metrics=FakeRetrievalMetrics(),
        source_repo=FakeSourceRepo(tenants=["waiting"], leased={"waiting": None}),
        outbox_repo=outbox_repo,
        embedding_service=embedding_service,
        source_registry=FakeSourceRegistry(None),
        outbox_registry=FakeOutboxRegistry(status="disabled"),
        process_outbox_batch=FakeOutboxRunner(),
        config=SchedulerConfig(component="scheduler", instance_id="i1", deployment_id="d1"),
    )

    await scheduler.run_cycle()

    assert embedding_service.calls == []
    assert outbox_repo.unblocked == []


@pytest.mark.asyncio
async def test_scheduler_refreshes_embedding_runtime_once_per_cycle():
    first_service = FakeEmbeddingService()
    second_service = FakeEmbeddingService()
    runtimes = iter([
        FakeEmbeddingRuntime(first_service, FakeOutboxRegistry(), "cfg-v1"),
        FakeEmbeddingRuntime(second_service, FakeOutboxRegistry(), "cfg-v2"),
    ])
    telemetry = FakeTelemetry()
    scheduler = Scheduler(
        telemetry=telemetry,
        retrieval_metrics=FakeRetrievalMetrics(),
        source_repo=FakeSourceRepo(tenants=["waiting"], leased={"waiting": None}),
        outbox_repo=FakeOutboxRepo(),
        embedding_service=None,
        source_registry=FakeSourceRegistry(None),
        outbox_registry=FakeOutboxRegistry(status="disabled"),
        embedding_runtime_factory=lambda: next(runtimes),
        process_outbox_batch=FakeOutboxRunner(),
        config=SchedulerConfig(component="scheduler", instance_id="i1", deployment_id="d1"),
    )

    await scheduler.run_cycle()
    await scheduler.run_cycle()

    assert first_service.calls == ["waiting"]
    assert second_service.calls == ["waiting"]
    cycle_starts = [item for item in telemetry.starts if item["operation"] == "cycle"]
    assert [item["config_version"] for item in cycle_starts] == ["cfg-v1", "cfg-v2"]


def test_scheduler_module_no_longer_exposes_daemon_entrypoints():
    import data_foundation.scheduler as scheduler

    assert not hasattr(scheduler, "_run_loop")
    assert not hasattr(scheduler, "start_background_services")


def test_build_scheduler_uses_explicit_embedding_env_profile(monkeypatch):
    import data_foundation.scheduler as scheduler

    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    captured = {}

    class FakeEmbeddingIndexService:
        def __init__(self, conn, *, profile):
            captured["profile"] = profile

    monkeypatch.setenv("XHS_EMBEDDING_API_KEY", "key")
    monkeypatch.setenv("XHS_EMBEDDING_BASE_URL", "https://embedding.example/v1")
    monkeypatch.setenv("XHS_EMBEDDING_MODEL", "model-from-env")
    monkeypatch.setenv("XHS_EMBEDDING_CONFIG_VERSION", "cfg-from-env")
    monkeypatch.setattr(scheduler, "connect", lambda: object())
    monkeypatch.setattr(scheduler, "ResourceRepository", lambda conn: object())
    monkeypatch.setattr(scheduler, "TelemetryRepository", lambda conn: FakeTelemetry())
    monkeypatch.setattr(scheduler, "SourceRepository", lambda conn: FakeSourceRepo(tenants=[]))
    monkeypatch.setattr(scheduler, "OutboxRepository", lambda conn: FakeOutboxRepo())
    monkeypatch.setattr(scheduler, "EmbeddingIndexService", FakeEmbeddingIndexService)
    monkeypatch.setattr(scheduler, "default_source_registry", lambda repo: FakeSourceRegistry(None))
    monkeypatch.setattr(
        scheduler,
        "default_processor_registry",
        lambda conn, **_kwargs: FakeOutboxRegistry(),
    )

    scheduler.build_scheduler()

    assert captured["profile"].embedding_model == "model-from-env"
    assert captured["profile"].config_version == "cfg-from-env"
    assert captured["profile"].chunker_version == "v1"


def test_build_scheduler_skips_embedding_service_for_invalid_env(monkeypatch):
    import data_foundation.scheduler as scheduler

    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    class FakeEmbeddingIndexService:
        def __init__(self, conn, *, profile):
            raise AssertionError("Embedding index service should not be built for invalid embedding config")

    monkeypatch.setenv("XHS_EMBEDDING_API_KEY", "key")
    monkeypatch.setenv("XHS_EMBEDDING_BASE_URL", "https://embedding.example/v1")
    monkeypatch.setenv("XHS_EMBEDDING_MODEL", "model-from-env")
    monkeypatch.setenv("XHS_EMBEDDING_DIMENSIONS", "3072")
    monkeypatch.setattr(scheduler, "connect", lambda: object())
    monkeypatch.setattr(scheduler, "ResourceRepository", lambda conn: object())
    monkeypatch.setattr(scheduler, "TelemetryRepository", lambda conn: FakeTelemetry())
    monkeypatch.setattr(scheduler, "SourceRepository", lambda conn: FakeSourceRepo(tenants=[]))
    monkeypatch.setattr(scheduler, "OutboxRepository", lambda conn: FakeOutboxRepo())
    monkeypatch.setattr(scheduler, "EmbeddingIndexService", FakeEmbeddingIndexService)
    monkeypatch.setattr(scheduler, "default_source_registry", lambda repo: FakeSourceRegistry(None))
    monkeypatch.setattr(
        scheduler,
        "default_processor_registry",
        lambda conn, **_kwargs: FakeOutboxRegistry(status="disabled"),
    )

    built = scheduler.build_scheduler()

    assert built.embedding_service is None


def test_build_scheduler_uses_disabled_embedding_service_without_explicit_env(monkeypatch):
    import data_foundation.scheduler as scheduler

    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    class FakeEmbeddingIndexService:
        def __init__(self, conn, *, profile):
            raise AssertionError("Embedding index service should not be built without explicit embedding config")

    monkeypatch.delenv("XHS_EMBEDDING_API_KEY", raising=False)
    monkeypatch.setattr(scheduler, "connect", lambda: object())
    monkeypatch.setattr(scheduler, "ResourceRepository", lambda conn: object())
    monkeypatch.setattr(scheduler, "TelemetryRepository", lambda conn: FakeTelemetry())
    monkeypatch.setattr(scheduler, "SourceRepository", lambda conn: FakeSourceRepo(tenants=[]))
    monkeypatch.setattr(scheduler, "OutboxRepository", lambda conn: FakeOutboxRepo())
    monkeypatch.setattr(scheduler, "EmbeddingIndexService", FakeEmbeddingIndexService)
    monkeypatch.setattr(scheduler, "default_source_registry", lambda repo: FakeSourceRegistry(None))
    monkeypatch.setattr(
        scheduler,
        "default_processor_registry",
        lambda conn, **_kwargs: FakeOutboxRegistry(status="disabled"),
    )

    built = scheduler.build_scheduler()

    assert built.embedding_service is None
