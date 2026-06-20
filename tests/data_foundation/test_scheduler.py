import pytest


def test_scheduler_disabled_by_default(monkeypatch):
    from data_foundation import scheduler

    scheduler._started = False
    monkeypatch.delenv("XHS_SYNC_ENABLED", raising=False)

    assert scheduler.should_start_scheduler() is False
    assert scheduler.start_background_services() is False
    assert scheduler._started is False


def test_scheduler_enabled_by_env_starts_daemon_thread_once(monkeypatch):
    from data_foundation import scheduler

    created_threads = []

    class FakeThread:
        def __init__(self, *, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False
            created_threads.append(self)

        def start(self):
            self.started = True

    scheduler._started = False
    monkeypatch.setenv("XHS_SYNC_ENABLED", "true")
    monkeypatch.setattr(scheduler.threading, "Thread", FakeThread)

    assert scheduler.should_start_scheduler() is True
    assert scheduler.start_background_services() is True
    assert scheduler.start_background_services() is False

    assert len(created_threads) == 1
    thread = created_threads[0]
    assert thread.target is scheduler._run_loop
    assert thread.name == "xhs-data-foundation-scheduler"
    assert thread.daemon is True
    assert thread.started is True


def test_scheduler_only_env_true_enables(monkeypatch):
    from data_foundation.scheduler import should_start_scheduler

    monkeypatch.setenv("XHS_SYNC_ENABLED", "1")

    assert should_start_scheduler() is False


def test_run_loop_processes_outbox_and_survives_batch_errors(monkeypatch):
    from data_foundation import scheduler

    class StopLoop(Exception):
        pass

    class FakeConnection:
        pass

    class FakeConnectContext:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeOutboxRepository:
        def __init__(self, conn):
            self.conn = conn

    sleeps = []
    calls = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise StopLoop

    class FakeRegistry:
        pass

    async def fake_process_outbox_batch(repo, *, tenant_id, registry, batch_size):
        assert isinstance(repo, FakeOutboxRepository)
        assert isinstance(registry, FakeRegistry)
        calls.append((tenant_id, batch_size))
        if len(calls) == 1:
            raise RuntimeError("temporary failure")
        return {"processed": 0}

    monkeypatch.setenv("XHS_SYNC_STARTUP_DELAY_SECONDS", "0")
    monkeypatch.setenv("XHS_OUTBOX_INTERVAL_SECONDS", "1")
    monkeypatch.setenv("XHS_OUTBOX_BATCH_SIZE", "7")
    monkeypatch.setattr(scheduler, "connect", lambda: FakeConnectContext())
    monkeypatch.setattr(scheduler, "OutboxRepository", FakeOutboxRepository)
    monkeypatch.setattr(scheduler, "ProcessorRegistry", FakeRegistry)
    monkeypatch.setattr(scheduler, "default_tenant_id", lambda: "tenant-test")
    monkeypatch.setattr(scheduler, "process_outbox_batch", fake_process_outbox_batch)
    monkeypatch.setattr(scheduler.time, "sleep", fake_sleep)

    with pytest.raises(StopLoop):
        scheduler._run_loop()

    assert calls == [("tenant-test", 7), ("tenant-test", 7)]
    assert sleeps == [0, 30, 30]
