from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re


SUMMARY_LIMIT = 240
DEFAULT_WINDOW_SECONDS = 60 * 60

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:postgresql|postgres)://\S+"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
)


@dataclass(frozen=True)
class ErrorClassification:
    error_code: str
    error_summary: str


def classify_error(
    exception: BaseException | None = None,
    *,
    message: str | None = None,
    component: str | None = None,
    operation: str | None = None,
) -> ErrorClassification:
    text = _classification_text(
        exception=exception,
        message=message,
        component=component,
        operation=operation,
    )
    summary = _summarize_error(exception=exception, message=message)
    return ErrorClassification(error_code=_classify_code(exception, text), error_summary=summary)


def build_error_aggregate_key(
    classification: ErrorClassification,
    *,
    occurred_at: datetime,
    tenant_id: str | None,
    component: str,
    operation: str | None,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> tuple[datetime, datetime, str | None, str, str | None, str]:
    window_started_at, window_ended_at = _window_bounds(occurred_at, window_seconds)
    return (
        window_started_at,
        window_ended_at,
        tenant_id,
        component,
        operation,
        classification.error_code,
    )


def build_error_aggregate_record(
    classification: ErrorClassification,
    *,
    occurred_at: datetime,
    tenant_id: str | None,
    component: str,
    operation: str | None,
    error_count: int = 1,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> dict[str, object]:
    if error_count < 1:
        raise ValueError("error_count must be positive")

    window_started_at, window_ended_at = _window_bounds(occurred_at, window_seconds)
    return {
        "window_started_at": window_started_at,
        "window_ended_at": window_ended_at,
        "tenant_id": tenant_id,
        "component": component,
        "operation": operation,
        "error_code": classification.error_code,
        "error_count": error_count,
    }


def _classify_code(exception: BaseException | None, text: str) -> str:
    if isinstance(exception, TimeoutError) or "timeout" in text or "timed out" in text:
        return "timeout"
    if (
        isinstance(exception, PermissionError)
        or "permission" in text
        or "forbidden" in text
        or "unauthorized" in text
    ):
        return "permission_denied"
    if (
        isinstance(exception, (ConnectionError, BrokenPipeError))
        or "connection" in text
        or "network" in text
    ):
        return "connection_error"
    if isinstance(exception, ValueError) or "invalid" in text or "unsupported" in text or "required" in text:
        return "invalid_input"
    return "internal_error"


def _classification_text(
    *,
    exception: BaseException | None,
    message: str | None,
    component: str | None,
    operation: str | None,
) -> str:
    parts = [
        message or "",
        str(exception) if exception is not None else "",
        component or "",
        operation or "",
    ]
    if exception is not None:
        parts.append(type(exception).__name__)
    return " ".join(parts).lower()


def _summarize_error(exception: BaseException | None, message: str | None) -> str:
    if message:
        raw = message
    elif exception is not None:
        raw = f"{type(exception).__name__}: {exception}"
    else:
        raw = "Unspecified error"

    first_line = raw.splitlines()[0] if raw.splitlines() else "Unspecified error"
    summary = _redact_secrets(" ".join(first_line.split()))
    return _limit_summary(summary)


def _redact_secrets(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    return redacted


def _redact_match(match: re.Match[str]) -> str:
    if match.lastindex:
        return f"{match.group(1)}=<redacted>"
    if "://" in match.group(0):
        return "<redacted-dsn>"
    return "Bearer <redacted>"


def _limit_summary(value: str, limit: int = SUMMARY_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _window_bounds(occurred_at: datetime, window_seconds: int) -> tuple[datetime, datetime]:
    if window_seconds < 1:
        raise ValueError("window_seconds must be positive")

    day_started_at = occurred_at.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_since_day_start = int((occurred_at - day_started_at).total_seconds())
    window_offset = seconds_since_day_start - (seconds_since_day_start % window_seconds)
    window_started_at = day_started_at + timedelta(seconds=window_offset)
    return window_started_at, window_started_at + timedelta(seconds=window_seconds)
