from __future__ import annotations

import re

from data_foundation.runtime_facts import supervisor_runtime_fact
from data_foundation.supervisor import BackgroundServiceSupervisor


def test_supervisor_fact_reports_safe_failed_cycle_state():
    supervisor = BackgroundServiceSupervisor(enabled=True)
    supervisor.instance_id = "instance-1"
    supervisor.last_cycle_started_at = "2026-06-20T00:00:00+00:00"
    supervisor.last_cycle_finished_at = "2026-06-20T00:00:01+00:00"
    supervisor.last_cycle_status = "failed"
    supervisor.last_cycle_error_code = "SCHEDULER_CYCLE_FAILED"

    fact = supervisor_runtime_fact(supervisor, observed_at="2026-06-20T00:00:02+00:00")

    assert fact == {
        "status": "degraded",
        "source": "instance",
        "observed_at": "2026-06-20T00:00:02+00:00",
        "stale_after_seconds": 60,
        "data": {
            "instance_id": "instance-1",
            "accepting_work": False,
            "last_cycle_started_at": "2026-06-20T00:00:00+00:00",
            "last_cycle_finished_at": "2026-06-20T00:00:01+00:00",
            "last_cycle_status": "failed",
        },
        "error": {
            "code": "SCHEDULER_CYCLE_FAILED",
            "summary": "Scheduler cycle failed",
        },
    }


def test_supervisor_cycle_metadata_is_safe_and_uses_utc_instance_id():
    supervisor = BackgroundServiceSupervisor(enabled=True)

    assert re.fullmatch(r"[0-9a-f]{32}", supervisor.instance_id)
    assert supervisor.last_cycle_started_at is None
    assert supervisor.last_cycle_finished_at is None
    assert supervisor.last_cycle_status is None
    assert supervisor.last_cycle_error_code is None
