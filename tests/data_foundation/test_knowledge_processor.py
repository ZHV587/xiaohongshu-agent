from datetime import UTC, datetime
import threading
from types import SimpleNamespace

import pytest

from data_foundation.knowledge.models import KnowledgeEnrichResult
from data_foundation.models import OutboxItem
from data_foundation.processors.base import PermanentProcessingError
from data_foundation.processors.knowledge import KnowledgeEnrichProcessor
from data_foundation.processors.preference import PreferenceSynthesizeProcessor
from data_foundation.processors.registry import ProcessorRegistry, default_processor_registry


def _item(payload=None, *, topic="knowledge_enrich"):
    now = datetime.now(UTC)
    return OutboxItem(
        id="job", tenant_id="tenant-a",
        resource_id=(
            "11111111-1111-1111-1111-111111111111"
            if topic == "knowledge_enrich"
            else None
        ),
        resource_version=2 if topic == "knowledge_enrich" else None,
        topic=topic, dedupe_key="d", payload=payload or {},
        status="processing", attempts=1, next_attempt_at=now,
        lease_owner="worker", lease_expires_at=now, error_code=None,
        error_summary=None, dead_at=None, created_at=now, updated_at=now,
    )


@pytest.mark.asyncio
async def test_knowledge_processor_renews_lease_and_delegates_exact_identity():
    calls = []

    class Service:
        def enrich_exact_version(self, **kwargs):
            calls.append(kwargs)
            return KnowledgeEnrichResult(
                status="qualified",
                resource_id=kwargs["resource_id"],
                resource_version=kwargs["resource_version"],
            )

    class Lease:
        async def assert_owned(self):
            calls.append("lease")

    result = await KnowledgeEnrichProcessor(None, service=Service()).process(_item(), Lease())

    assert calls == [
        "lease",
        {
            "tenant_id": "tenant-a",
            "resource_id": "11111111-1111-1111-1111-111111111111",
            "resource_version": 2,
        },
        "lease",
    ]
    assert result.status == "succeeded"


@pytest.mark.asyncio
async def test_preference_processor_renews_around_actor_pattern_synthesis():
    calls = []

    class Service:
        def synthesize_patterns(self, **kwargs):
            calls.append(("patterns", kwargs))
            return [{"pattern_key": "hook:反常识"}]

        def mark_synthesis_completed(self, **kwargs):
            calls.append(("completed", kwargs))
            return True

    class Lease:
        async def assert_owned(self):
            calls.append("lease")

    result = await PreferenceSynthesizeProcessor(
        None, service=Service()
    ).process(
        _item(
            {"actor_open_id": "ou-owner", "requested_revision": 3},
            topic="preference_synthesize",
        ),
        Lease(),
    )

    assert result.status == "succeeded"
    assert result.processed_count == 1
    assert calls == [
        "lease",
        (
            "patterns",
            {"tenant_id": "tenant-a", "actor_open_id": "ou-owner"},
        ),
        "lease",
        (
            "completed",
            {
                "tenant_id": "tenant-a",
                "actor_open_id": "ou-owner",
                "requested_revision": 3,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_preference_processor_rejects_missing_actor():
    class Lease:
        async def assert_owned(self):
            return None

    with pytest.raises(PermanentProcessingError, match="actor_open_id"):
        await PreferenceSynthesizeProcessor(
            None, service=SimpleNamespace()
        ).process(_item(topic="preference_synthesize"), Lease())


@pytest.mark.asyncio
async def test_preference_processor_owns_connections_separate_from_scheduler(monkeypatch):
    from data_foundation.processors import preference as preference_processor

    connections = []

    class Connection:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class Service:
        def __init__(self, repo):
            self.connection = repo.conn

        def synthesize_patterns(self, **_kwargs):
            return []

        def mark_synthesis_completed(self, **_kwargs):
            return True

    def connection_factory():
        connection = Connection()
        connections.append(connection)
        return connection

    class Lease:
        async def assert_owned(self):
            return None

    monkeypatch.setattr(preference_processor, "PreferenceLearningService", Service)
    await PreferenceSynthesizeProcessor(
        SimpleNamespace(name="scheduler-connection"),
        connection_factory=connection_factory,
    ).process(
        _item(
            {"actor_open_id": "ou-owner", "requested_revision": 1},
            topic="preference_synthesize",
        ),
        Lease(),
    )

    assert len(connections) == 2
    assert all(connection.closed for connection in connections)


@pytest.mark.asyncio
async def test_preference_processor_waits_for_worker_thread_after_lease_loss(monkeypatch):
    from data_foundation.processors import preference as preference_processor

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class Service:
        def synthesize_patterns(self, **_kwargs):
            started.set()
            release.wait(timeout=2)
            finished.set()
            return []

    class Lease:
        lease_seconds = 60

        def __init__(self):
            self.calls = 0

        async def assert_owned(self):
            self.calls += 1
            if self.calls == 1:
                return None
            release.set()
            raise RuntimeError("LEASE_LOST")

    async def immediate_heartbeat(tasks, *, timeout):
        assert timeout > 0
        started.wait(timeout=1)
        return set(), set(tasks)

    monkeypatch.setattr(preference_processor.asyncio, "wait", immediate_heartbeat)
    with pytest.raises(RuntimeError, match="LEASE_LOST"):
        await PreferenceSynthesizeProcessor(None, service=Service()).process(
            _item(
                {"actor_open_id": "ou-owner", "requested_revision": 1},
                topic="preference_synthesize",
            ),
            Lease(),
        )

    assert finished.is_set()


def test_registry_declares_knowledge_enrich_as_first_class_topic():
    assert "knowledge_enrich" in ProcessorRegistry().topics
    assert "preference_synthesize" in ProcessorRegistry().topics


def test_default_registry_installs_always_active_knowledge_processor(monkeypatch):
    # The registry eagerly creates configured external engines. This unit test only
    # exercises always-active local processors and must not inherit production .env.
    monkeypatch.setenv("XHS_MEILI_URL", "")
    monkeypatch.setenv("XHS_MEILI_KEY", "")
    monkeypatch.setenv("XHS_FALKOR_URL", "")
    monkeypatch.setenv("XHS_FALKOR_GRAPH", "")
    monkeypatch.setattr(
        "data_foundation.processors.registry.embedding_config_from_runtime",
        lambda: None,
    )
    registry = default_processor_registry(SimpleNamespace(), embedding_config=None)
    processor = registry.processor_for("knowledge_enrich")
    assert processor is not None
    assert processor.state().status == "active"
    preference = registry.processor_for("preference_synthesize")
    assert preference is not None
    assert preference.state().status == "active"
