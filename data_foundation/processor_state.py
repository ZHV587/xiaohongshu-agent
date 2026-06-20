from __future__ import annotations

from dataclasses import dataclass

from data_foundation.models import ProcessorState


ACTIVE_STATUSES = frozenset({"enabled", "active", "running"})
FAILED_OR_BLOCKED_STATUSES = frozenset({"disabled", "misconfigured", "failed", "blocked"})


@dataclass(frozen=True)
class ProcessorStateSnapshot:
    topic: str
    status: str
    config_version: str | None
    reason_code: str | None
    active: bool
    stale_config: bool
    failed_or_blocked: bool


def normalize_config_version(config_version: str) -> str:
    if not isinstance(config_version, str):
        raise TypeError("config_version must be a string")
    normalized = config_version.strip()
    if not normalized:
        raise ValueError("config_version must be a non-empty string")
    return normalized


def derive_processor_snapshot(
    state: ProcessorState,
    *,
    current_config_version: str | None = None,
) -> ProcessorStateSnapshot:
    state_config_version = (
        normalize_config_version(state.config_version)
        if state.config_version is not None
        else None
    )
    expected_config_version = (
        normalize_config_version(current_config_version)
        if current_config_version is not None
        else None
    )
    active = state.status in ACTIVE_STATUSES and state.reason_code is None
    stale_config = (
        active
        and state_config_version is not None
        and expected_config_version is not None
        and state_config_version != expected_config_version
    )
    failed_or_blocked = state.status in FAILED_OR_BLOCKED_STATUSES or state.reason_code is not None
    return ProcessorStateSnapshot(
        topic=state.topic,
        status=state.status,
        config_version=state_config_version,
        reason_code=state.reason_code,
        active=active,
        stale_config=stale_config,
        failed_or_blocked=failed_or_blocked,
    )


def is_processor_active(state: ProcessorState) -> bool:
    return derive_processor_snapshot(state).active


def is_stale_config(state: ProcessorState, *, current_config_version: str | None) -> bool:
    return derive_processor_snapshot(
        state,
        current_config_version=current_config_version,
    ).stale_config


def is_failed_or_blocked(state: ProcessorState) -> bool:
    return derive_processor_snapshot(state).failed_or_blocked
