from __future__ import annotations

import pytest

from data_foundation.models import ProcessorState
import data_foundation.processor_state as processor_state
from data_foundation.processor_state import (
    derive_processor_snapshot,
    is_failed_or_blocked,
    is_processor_active,
    is_stale_config,
    normalize_config_version,
)


def test_config_version_requires_non_empty_string_and_preserves_numeric_text():
    assert normalize_config_version("cfg-2026-06-20") == "cfg-2026-06-20"
    assert normalize_config_version("001") == "001"

    with pytest.raises(ValueError, match="non-empty"):
        normalize_config_version(" ")
    with pytest.raises(TypeError, match="string"):
        normalize_config_version(1)


def test_processor_snapshot_derives_active_and_stale_config():
    state = ProcessorState(
        topic="embedding_generate",
        status="enabled",
        config_version="001",
        reason_code=None,
    )
    snapshot = derive_processor_snapshot(
        state,
        current_config_version="002",
    )

    assert snapshot.topic == "embedding_generate"
    assert snapshot.status == "enabled"
    assert snapshot.config_version == "001"
    assert snapshot.active is True
    assert snapshot.stale_config is True
    assert snapshot.failed_or_blocked is False
    assert is_processor_active(state) is True
    assert is_stale_config(state, current_config_version="002") is True
    assert is_failed_or_blocked(state) is False


@pytest.mark.parametrize(
    "status, reason_code",
    [
        ("disabled", "PROCESSOR_DISABLED"),
        ("misconfigured", "EMBEDDING_CONFIG_INVALID"),
        ("failed", None),
        ("blocked", "AUTH_INVALID"),
    ],
)
def test_processor_snapshot_derives_failed_or_blocked(status: str, reason_code: str | None):
    snapshot = derive_processor_snapshot(
        ProcessorState(
            topic="embedding_generate",
            status=status,
            config_version="cfg",
            reason_code=reason_code,
        ),
        current_config_version="cfg",
    )

    assert snapshot.active is False
    assert snapshot.stale_config is False
    assert snapshot.failed_or_blocked is True


def test_reason_code_prevents_active_state_even_when_status_is_enabled():
    state = ProcessorState(
        topic="embedding_generate",
        status="enabled",
        config_version="cfg",
        reason_code="AUTH_INVALID",
    )

    snapshot = derive_processor_snapshot(state, current_config_version="cfg")

    assert snapshot.active is False
    assert snapshot.failed_or_blocked is True
    assert is_processor_active(state) is False


def test_processor_state_helpers_do_not_import_database_layers():
    forbidden = {
        "data_foundation.db",
        "data_foundation.repositories",
        "data_foundation.outbox_worker",
        "data_foundation.sync_service",
    }
    referenced_modules = {
        value.__name__
        for value in processor_state.__dict__.values()
        if getattr(value, "__name__", "").startswith("data_foundation.")
    }

    assert forbidden.isdisjoint(referenced_modules)
