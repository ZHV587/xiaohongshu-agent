import asyncio
import os
import sys
import pytest
import psycopg
from data_foundation.db import connect
from data_foundation.supervisor import BackgroundServiceSupervisor

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

@pytest.mark.asyncio
async def test_supervisor_listener_wake_event(migrated_conn, monkeypatch):
    schema_row = migrated_conn.execute("SELECT current_schema()").fetchone()
    schema = schema_row[0] if (schema_row and schema_row[0]) else "public"
    
    # Propagate the test schema search path to the supervisor listener connection via XHS_DATABASE_URL
    base_url = os.environ.get("XHS_DATABASE_URL") or os.environ.get("TEST_XHS_DATABASE_URL")
    sep = "&" if "?" in base_url else "?"
    patched_url = f"{base_url}{sep}options=-csearch_path%3D{schema}"
    monkeypatch.setenv("XHS_DATABASE_URL", patched_url)
    
    supervisor = BackgroundServiceSupervisor(enabled=True)
    supervisor.accepting_work = True
    supervisor._wake_event.clear()
    
    supervisor._listener_task = asyncio.create_task(supervisor._listen_db_notifies())
    
    # Wait for listener to connect
    await asyncio.sleep(0.5)
    
    # Send mock notify
    with connect() as conn:
        conn.autocommit = True
        conn.execute(f"NOTIFY outbox_work_{schema}, 'test_tenant'")
        
    try:
        await asyncio.wait_for(supervisor._wake_event.wait(), timeout=2.0)
        assert supervisor._wake_event.is_set()
    finally:
        supervisor.accepting_work = False
        if supervisor._listener_task:
            supervisor._listener_task.cancel()
            try:
                await supervisor._listener_task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_supervisor_outbox_trigger_wakeup(migrated_conn, monkeypatch):
    schema_row = migrated_conn.execute("SELECT current_schema()").fetchone()
    schema = schema_row[0] if (schema_row and schema_row[0]) else "public"
    
    # Propagate test schema search path
    base_url = os.environ.get("XHS_DATABASE_URL") or os.environ.get("TEST_XHS_DATABASE_URL")
    sep = "&" if "?" in base_url else "?"
    patched_url = f"{base_url}{sep}options=-csearch_path%3D{schema}"
    monkeypatch.setenv("XHS_DATABASE_URL", patched_url)
    
    cycle_run_count = 0
    cycle_done = asyncio.Event()
    
    class MockScheduler:
        def __init__(self):
            self.telemetry = None
            self.config = None
        async def run_cycle(self):
            nonlocal cycle_run_count
            cycle_run_count += 1
            cycle_done.set()
            from data_foundation.scheduler import CycleStats
            return CycleStats()
        def stop(self):
            pass
            
    supervisor = BackgroundServiceSupervisor(
        scheduler_factory=MockScheduler,
        enabled=True,
        interval_seconds=10.0
    )
    
    await supervisor.start()
    # Let it run initial cycle and connect listener
    await asyncio.sleep(0.5)
    cycle_done.clear()
    
    # Insert resources for foreign keys in outbox
    import uuid
    resource_id = uuid.uuid4()
    
    migrated_conn.execute(
        "insert into resources (tenant_id, id, type, title, summary, content_text) "
        "values ('tenant_test', %s, 'note', 'title', 'summary', 'content')",
        (resource_id,)
    )
    migrated_conn.execute(
        "insert into resource_versions (tenant_id, resource_id, version, content_text, content_hash) "
        "values ('tenant_test', %s, 1, 'content', 'hash')",
        (resource_id,)
    )
    migrated_conn.commit()
    
    # Insert pending outbox record
    migrated_conn.execute(
        "insert into resource_outbox (tenant_id, resource_id, resource_version, topic, dedupe_key, payload, status) "
        "values ('tenant_test', %s, 1, 'meili_index', 'dedupe_key_1', '{}'::jsonb, 'pending')",
        (resource_id,)
    )
    migrated_conn.commit()
    
    try:
        # Verify that supervisor wakes up and executes immediately (timeout = 3.0s, far less than interval=10.0)
        await asyncio.wait_for(cycle_done.wait(), timeout=3.0)
        assert cycle_run_count >= 1
    finally:
        await supervisor.stop()
