from __future__ import annotations

import asyncio
import os
import threading
import time

from data_foundation.db import connect
from data_foundation.outbox_repository import OutboxRepository
from data_foundation.outbox_worker import process_outbox_batch
from data_foundation.permissions import default_tenant_id
from data_foundation.processors.registry import default_processor_registry


_started = False


def should_start_scheduler() -> bool:
    return os.environ.get("XHS_SYNC_ENABLED", "false").strip().lower() == "true"


def start_background_services() -> bool:
    global _started
    if _started or not should_start_scheduler():
        return False

    _started = True
    thread = threading.Thread(target=_run_loop, name="xhs-data-foundation-scheduler", daemon=True)
    thread.start()
    return True


def _run_loop() -> None:
    startup_delay = int(os.environ.get("XHS_SYNC_STARTUP_DELAY_SECONDS", "30"))
    interval = int(os.environ.get("XHS_OUTBOX_INTERVAL_SECONDS", "300"))
    batch_size = int(os.environ.get("XHS_OUTBOX_BATCH_SIZE", "20"))

    time.sleep(max(0, startup_delay))
    while True:
        try:
            with connect() as conn:
                repo = OutboxRepository(conn)
                asyncio.run(
                    process_outbox_batch(
                        repo,
                        tenant_id=default_tenant_id(),
                        registry=default_processor_registry(conn),
                        batch_size=batch_size,
                    )
                )
        except Exception:
            pass
        time.sleep(max(30, interval))
