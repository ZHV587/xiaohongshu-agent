from datetime import UTC, datetime

from data_foundation.errors import (
    build_error_aggregate_key,
    build_error_aggregate_record,
    classify_error,
)


def test_classify_error_returns_stable_code_and_sanitized_summary():
    long_secret = "x" * 500
    exc = TimeoutError(
        "Request timed out\n"
        'Traceback (most recent call last):\n  File "worker.py", line 9\n'
        f"api_key={long_secret}"
    )

    classification = classify_error(
        exc,
        component="outbox_worker",
        operation="embedding_generate",
    )

    assert classification.error_code == "timeout"
    assert classification.error_summary.startswith("TimeoutError: Request timed out")
    assert "Traceback" not in classification.error_summary
    assert "worker.py" not in classification.error_summary
    assert long_secret not in classification.error_summary
    assert len(classification.error_summary) <= 240


def test_classify_error_uses_message_without_exception_and_normalizes_unknowns():
    classification = classify_error(
        message="database connection refused by host",
        component="repository",
        operation="write_resource",
    )

    assert classification.error_code == "connection_error"
    assert classification.error_summary == "database connection refused by host"

    fallback = classify_error(component="scheduler", operation="tick")

    assert fallback.error_code == "internal_error"
    assert fallback.error_summary == "Unspecified error"


def test_classify_error_redacts_postgres_dsn():
    classification = classify_error(
        message="connect failed postgresql://user:secret@db.example:5432/app",
        component="postgres_source",
        operation="sync",
    )

    assert "secret" not in classification.error_summary
    assert "postgresql://user" not in classification.error_summary
    assert "<redacted-dsn>" in classification.error_summary


def test_build_error_aggregate_key_uses_schema_dimensions_and_hour_window():
    occurred_at = datetime(2026, 6, 20, 10, 37, 42, tzinfo=UTC)
    classification = classify_error(ValueError("bad chunk"), component="search", operation="embed")

    key = build_error_aggregate_key(
        classification,
        occurred_at=occurred_at,
        tenant_id="tenant-a",
        component="search",
        operation="embed",
    )

    assert key == (
        datetime(2026, 6, 20, 10, 0, tzinfo=UTC),
        datetime(2026, 6, 20, 11, 0, tzinfo=UTC),
        "tenant-a",
        "search",
        "embed",
        "invalid_input",
    )


def test_build_error_aggregate_record_matches_service_error_aggregates_shape():
    occurred_at = datetime(2026, 6, 20, 10, 59, 59)
    classification = classify_error(PermissionError("denied"), component="tools", operation=None)

    record = build_error_aggregate_record(
        classification,
        occurred_at=occurred_at,
        tenant_id=None,
        component="tools",
        operation=None,
        error_count=3,
    )

    assert record == {
        "window_started_at": datetime(2026, 6, 20, 10, 0),
        "window_ended_at": datetime(2026, 6, 20, 11, 0),
        "tenant_id": None,
        "component": "tools",
        "operation": None,
        "error_code": "permission_denied",
        "error_count": 3,
    }
