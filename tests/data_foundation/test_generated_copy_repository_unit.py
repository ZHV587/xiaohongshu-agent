from __future__ import annotations

from contextlib import nullcontext
import hashlib
import inspect
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from data_foundation.repositories.generated_copy import (
    GeneratedCopyConflict,
    GeneratedCopyRepository,
)
from data_foundation.repositories.resource import ResourceRepository


def test_select_version_hydrates_label_without_name_error(monkeypatch):
    repo = GeneratedCopyRepository.__new__(GeneratedCopyRepository)
    repo.conn = MagicMock()
    repo.conn.transaction.return_value = nullcontext()
    repo.resource_repo = MagicMock()
    current = SimpleNamespace(
        lifecycle_status="candidate", state_version=1, latest_resource_version=3
    )
    monkeypatch.setattr(repo, "_lock_and_authorize", lambda **kwargs: current)
    monkeypatch.setattr(repo, "_assert_version", lambda **kwargs: None)
    monkeypatch.setattr(repo, "_version_label", lambda **kwargs: "B")
    monkeypatch.setattr(repo, "_event", lambda **kwargs: "event-1")
    expected = object()
    monkeypatch.setattr(repo, "_state_with_latest", lambda row: expected)
    repo.conn.execute.return_value.fetchone.return_value = {"resource_id": "r1"}

    result = repo.select_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="r1",
        resource_version=2,
        expected_state_version=1,
    )

    assert result is expected
    update_args = repo.conn.execute.call_args_list[0].args[1]
    assert update_args[:2] == (2, "B")

    with pytest.raises(ValueError, match="does not match"):
        repo.select_version(
            tenant_id="default",
            actor_open_id="ou_user",
            resource_id="r1",
            resource_version=2,
            expected_state_version=1,
            label="forged-label",
        )


@pytest.mark.parametrize("status", ["finalized", "published", "measured"])
def test_terminal_lifecycle_rejects_mutating_actions(status):
    state = SimpleNamespace(lifecycle_status=status)
    for action in ("select", "revise", "adopt"):
        with pytest.raises(GeneratedCopyConflict, match=f"cannot {action}"):
            GeneratedCopyRepository._ensure_mutable(state, action=action)


def test_version_hydration_contract_uses_acl_and_resource_versions():
    source = inspect.getsource(ResourceRepository.get_resource_version)
    assert "readable_resource_where" in source
    assert "resource_versions rv" in source
    assert "rv.content_text" in source
    assert "rv.content_json" in source


def test_meili_and_agent_hydration_fail_closed_on_generated_copy_pointer():
    meili_source = inspect.getsource(ResourceRepository.readable_rows_by_ids)
    assert "resource_versions must align with resource_ids" in meili_source
    assert "rv.version = req.resource_version" in meili_source
    assert "gcs.knowledge_target_version = rv.version" in meili_source
    assert "rv.content_text" in meili_source
    assert "when r.type = 'generated_copy' then gcs.knowledge_target_version" in meili_source

    agent_source = inspect.getsource(ResourceRepository.get_resource_for_knowledge)
    assert "readable_resource_where" in agent_source
    assert "then gcs.knowledge_target_version" in agent_source
    assert "rv.content_text" in agent_source

    revision_source = inspect.getsource(GeneratedCopyRepository._append_revision)
    assert "get_resource_version" in revision_source
    assert "base_resource_version" in revision_source
    assert ".get_resource(" not in revision_source


def test_lifecycle_versions_are_exact_ordered_snapshots_with_stable_labels():
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "version": 1,
            "content_json": {
                "variant_label": "A",
                "title": "A old",
                "body": "old body",
                "tags": ["#old", 3],
                "cover": "old cover",
                "note": "old note",
            },
        },
        {
            "version": 2,
            "content_json": {
                "variant_label": "A",
                "title": "A final",
                "body": "final body",
                "tags": ["#final"],
            },
        },
    ]
    resource_repo = SimpleNamespace(
        conn=conn,
        writable_resource_metadata=lambda **_kwargs: {"type": "generated_copy"},
    )
    lifecycle = GeneratedCopyRepository(resource_repo)

    versions = lifecycle.list_versions(
        tenant_id="default", actor_open_id="ou_owner", resource_id="copy-1"
    )

    assert versions == [
        {
            "resourceVersion": 1,
            "label": "A",
            "title": "A old",
            "body": "old body",
            "tags": ["#old"],
            "cover": "old cover",
            "note": "old note",
        },
        {
            "resourceVersion": 2,
            "label": "A",
            "title": "A final",
            "body": "final body",
            "tags": ["#final"],
            "cover": "",
            "note": "",
        },
    ]


def _repo_with_locked_state(monkeypatch, current):
    repo = GeneratedCopyRepository.__new__(GeneratedCopyRepository)
    repo.conn = MagicMock()
    repo.conn.transaction.return_value = nullcontext()
    repo.resource_repo = MagicMock()
    monkeypatch.setattr(repo, "_lock_and_authorize", lambda **_kwargs: current)
    return repo


def test_final_draft_retry_replays_before_stale_cas_and_does_not_append(monkeypatch):
    draft = {"title": "Final", "body": "Exact body", "tags": ["#final"]}
    normalized = GeneratedCopyRepository._normalize_revision_payload(draft)
    fingerprint = hashlib.sha256(
        json.dumps(
            normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    current = SimpleNamespace(
        lifecycle_status="finalized",
        finalized_version=2,
        finalize_request_id="schedule-1",
        finalize_draft_hash=fingerprint,
        finalize_base_version=1,
    )
    repo = _repo_with_locked_state(monkeypatch, current)
    append = MagicMock()
    monkeypatch.setattr(repo, "_append_revision", append)

    replay = repo.finalize_for_schedule(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_id="copy-1",
        target_resource_version=1,
        expected_latest_resource_version=1,
        expected_state_version=1,
        final_draft=draft,
        request_id="schedule-1",
    )

    assert replay is current
    append.assert_not_called()
    repo.conn.execute.assert_not_called()

    with pytest.raises(GeneratedCopyConflict, match="reused with a different draft"):
        repo.finalize_for_schedule(
            tenant_id="default",
            actor_open_id="ou_owner",
            resource_id="copy-1",
            target_resource_version=1,
            expected_latest_resource_version=1,
            expected_state_version=1,
            final_draft={"title": "Changed", "body": "Changed body", "tags": []},
            request_id="schedule-1",
        )


def test_exact_finalized_retry_ignores_stale_cas_but_rejects_replacement(monkeypatch):
    current = SimpleNamespace(
        lifecycle_status="finalized",
        finalized_version=2,
        finalize_request_id=None,
        finalize_draft_hash=None,
        finalize_base_version=None,
    )
    repo = _repo_with_locked_state(monkeypatch, current)
    assert repo.finalize_for_schedule(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_id="copy-1",
        target_resource_version=2,
        expected_latest_resource_version=2,
        expected_state_version=1,
    ) is current
    with pytest.raises(GeneratedCopyConflict, match="cannot be replaced"):
        repo.finalize_for_schedule(
            tenant_id="default",
            actor_open_id="ou_owner",
            resource_id="copy-1",
            target_resource_version=1,
            expected_latest_resource_version=2,
            expected_state_version=1,
        )


def test_schedule_validates_state_latest_and_selected_as_distinct_cas_dimensions(monkeypatch):
    current = SimpleNamespace(
        lifecycle_status="selected",
        state_version=3,
        latest_resource_version=2,
        selected_version=1,
    )
    repo = _repo_with_locked_state(monkeypatch, current)

    with pytest.raises(GeneratedCopyConflict, match="state version changed"):
        repo.finalize_for_schedule(
            tenant_id="default",
            actor_open_id="ou_owner",
            resource_id="copy-1",
            target_resource_version=1,
            expected_latest_resource_version=2,
            expected_state_version=2,
        )
    with pytest.raises(GeneratedCopyConflict, match="latest resource version changed"):
        repo.finalize_for_schedule(
            tenant_id="default",
            actor_open_id="ou_owner",
            resource_id="copy-1",
            target_resource_version=1,
            expected_latest_resource_version=1,
            expected_state_version=3,
        )
    with pytest.raises(GeneratedCopyConflict, match="must match selected_version 1"):
        repo.finalize_for_schedule(
            tenant_id="default",
            actor_open_id="ou_owner",
            resource_id="copy-1",
            target_resource_version=2,
            expected_latest_resource_version=2,
            expected_state_version=3,
        )


def test_published_and_measured_terminal_retries_are_idempotent(monkeypatch):
    published = SimpleNamespace(lifecycle_status="published")
    published_repo = _repo_with_locked_state(monkeypatch, published)
    published_event = MagicMock()
    monkeypatch.setattr(published_repo, "_event", published_event)
    assert published_repo.mark_published(
        tenant_id="default", actor_open_id="ou_owner", resource_id="copy-1"
    ) is published
    published_repo.conn.execute.assert_not_called()
    published_event.assert_not_called()

    measured = SimpleNamespace(lifecycle_status="measured")
    repo = _repo_with_locked_state(monkeypatch, measured)
    event = MagicMock()
    monkeypatch.setattr(repo, "_event", event)

    assert repo.mark_published(
        tenant_id="default", actor_open_id="ou_owner", resource_id="copy-1"
    ) is measured
    assert repo.mark_measured(
        tenant_id="default", actor_open_id="ou_owner", resource_id="copy-1"
    ) is measured
    repo.conn.execute.assert_not_called()
    event.assert_not_called()


def test_performance_attribution_accepts_only_exact_published_version(monkeypatch):
    repo = GeneratedCopyRepository.__new__(GeneratedCopyRepository)
    current = SimpleNamespace(published_version=3)
    monkeypatch.setattr(repo, "get_state", lambda **_kwargs: current)

    assert repo.attributable_version(
        tenant_id="default", actor_open_id="ou_owner", resource_id="copy-1"
    ) == 3
    assert repo.attributable_version(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_id="copy-1",
        requested_version=3,
    ) == 3
    with pytest.raises(GeneratedCopyConflict, match="published_version exactly"):
        repo.attributable_version(
            tenant_id="default",
            actor_open_id="ou_owner",
            resource_id="copy-1",
            requested_version=2,
        )

    monkeypatch.setattr(
        repo, "get_state", lambda **_kwargs: SimpleNamespace(published_version=None)
    )
    with pytest.raises(GeneratedCopyConflict, match="exactly published"):
        repo.attributable_version(
            tenant_id="default", actor_open_id="ou_owner", resource_id="copy-1"
        )
