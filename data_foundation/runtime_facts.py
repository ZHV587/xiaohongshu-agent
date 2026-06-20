from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


SCHEDULER_CYCLE_FAILED = "SCHEDULER_CYCLE_FAILED"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def module_fact(
    *,
    status: str,
    source: str,
    observed_at: str,
    stale_after_seconds: int,
    data: dict,
    error: dict | None = None,
) -> dict:
    result = {
        "status": status,
        "source": source,
        "observed_at": observed_at,
        "stale_after_seconds": stale_after_seconds,
        "data": data,
    }
    if error is not None:
        result["error"] = error
    return result


@dataclass
class RuntimeSnapshot:
    instance_id: str
    started_at: str
    status: str = "running"
    stopped_at: str | None = None

    def stop(self, *, observed_at: str) -> None:
        self.status = "stopped"
        self.stopped_at = observed_at


def create_runtime_snapshot(supervisor, *, observed_at: str | None = None) -> RuntimeSnapshot:
    return RuntimeSnapshot(instance_id=supervisor.instance_id, started_at=observed_at or utc_now())


def supervisor_runtime_fact(supervisor, *, observed_at: str) -> dict:
    cycle_status = supervisor.last_cycle_status or "never_run"
    status = "unavailable" if not supervisor.enabled else "degraded" if cycle_status == "failed" else "healthy"
    error = None
    if supervisor.last_cycle_error_code is not None:
        error = {
            "code": supervisor.last_cycle_error_code,
            "summary": "Scheduler cycle failed",
        }
    return module_fact(
        status=status,
        source="instance",
        observed_at=observed_at,
        stale_after_seconds=max(30, int(supervisor.interval_seconds * 2)),
        data={
            "instance_id": supervisor.instance_id,
            "accepting_work": supervisor.accepting_work,
            "last_cycle_started_at": supervisor.last_cycle_started_at,
            "last_cycle_finished_at": supervisor.last_cycle_finished_at,
            "last_cycle_status": cycle_status,
        },
        error=error,
    )
