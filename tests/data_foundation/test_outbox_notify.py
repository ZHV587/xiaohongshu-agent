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
    base_url = os.environ.get("XHS_DATABASE_URL")
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
