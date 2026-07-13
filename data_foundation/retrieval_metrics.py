"""Safe online measurements for unified knowledge retrieval.

The service is intentionally a narrow adapter between the DeepAgents trace middleware
and PostgreSQL.  It projects an ``EvidencePackage`` result onto a fixed numeric/exact-
identity contract before opening a database connection; query text, evidence text,
provider errors and arbitrary result fields therefore never cross the repository API.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import logging
import math
import threading
from typing import Any, Callable, Mapping
import uuid

from data_foundation.db import connect
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.retrieval_contract import is_retrieval_error_result
from data_foundation.repositories.retrieval_metrics import (
    RETRIEVAL_MODES,
    RecordedRetrieval,
    RetrievalExposure,
    RetrievalMeasurement,
    RetrievalMetricsRepository,
    RetrievalOutcomeMetrics,
    exact_evidence_key,
)


_RECALL_ENGINES = frozenset({"semantic", "keyword", "graph"})
_METRIC_CONNECT_TIMEOUT_SECONDS = 2
_METRIC_STATEMENT_TIMEOUT_MS = 2000
_METRIC_LOCK_TIMEOUT_MS = 500
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedRetrievalMetric:
    """Fixed, content-free payload allowed to cross the background queue boundary."""

    measurement: RetrievalMeasurement
    exact_identities: tuple[tuple[str, str, int], ...]

    def identity_map(self) -> dict[str, tuple[str, int]]:
        return {
            evidence_key: (resource_id, resource_version)
            for evidence_key, resource_id, resource_version in self.exact_identities
        }


@dataclass(frozen=True)
class RetrievalMetricDispatcherStats:
    accepted: int
    dropped: int
    write_failed: int


class BoundedRetrievalMetricDispatcher:
    """Best-effort writer whose active and queued work is strictly bounded."""

    def __init__(
        self,
        writer: Callable[[PreparedRetrievalMetric], Any],
        *,
        max_workers: int = 2,
        max_in_flight: int = 64,
    ) -> None:
        if max_workers <= 0 or max_in_flight < max_workers:
            raise ValueError("max_in_flight must be at least max_workers")
        self._writer = writer
        self._permits = threading.BoundedSemaphore(max_in_flight)
        self._stats_lock = threading.Lock()
        self._accepted = 0
        self._dropped = 0
        self._write_failed = 0
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="xhs-retrieval-metric",
        )

    def submit(self, prepared: PreparedRetrievalMetric) -> bool:
        if not isinstance(prepared, PreparedRetrievalMetric):
            raise TypeError("prepared retrieval metric is required")
        if not self._permits.acquire(blocking=False):
            self._record_drop()
            return False
        try:
            future = self._executor.submit(self._write_safely, prepared)
        except RuntimeError:
            self._permits.release()
            self._record_drop()
            return False
        with self._stats_lock:
            self._accepted += 1
        future.add_done_callback(lambda _future: self._permits.release())
        return True

    def _write_safely(self, prepared: PreparedRetrievalMetric) -> None:
        try:
            self._writer(prepared)
        except Exception as exc:  # noqa: BLE001 - metrics are best effort
            with self._stats_lock:
                self._write_failed += 1
                write_failed = self._write_failed
            if write_failed & (write_failed - 1) == 0:
                logger.warning(
                    "retrieval metric background writes failed: %s count=%d",
                    type(exc).__name__,
                    write_failed,
                )

    def _record_drop(self) -> None:
        with self._stats_lock:
            self._dropped += 1
            dropped = self._dropped
        # Powers-of-two logging keeps overload visible without turning it into a log
        # amplification path. The message contains only a process-local count.
        if dropped & (dropped - 1) == 0:
            logger.warning("retrieval metric queue dropped measurements: %d", dropped)

    def stats(self) -> RetrievalMetricDispatcherStats:
        with self._stats_lock:
            return RetrievalMetricDispatcherStats(
                accepted=self._accepted,
                dropped=self._dropped,
                write_failed=self._write_failed,
            )

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


_GLOBAL_DISPATCHER: BoundedRetrievalMetricDispatcher | None = None
_GLOBAL_DISPATCHER_LOCK = threading.Lock()
_GLOBAL_DISPATCHER_CLOSED = False


def correlation_key(value: str) -> str:
    """Return an irreversible stable key for a runtime correlation identifier."""

    if not isinstance(value, str) or not value:
        raise ValueError("correlation identifier is required")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RetrievalMetricsService:
    def __init__(self, repository: RetrievalMetricsRepository):
        self.repository = repository

    def record_trace_result(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        trace_identity: Mapping[str, str | None],
        tool_call_id: str,
        latency_ms: int,
        result: Any,
    ) -> RecordedRetrieval | None:
        prepared = _prepare_measurement_from_result(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            trace_identity=trace_identity,
            tool_call_id=tool_call_id,
            latency_ms=latency_ms,
            result=result,
        )
        if prepared is None:
            return None
        return self.repository.record(
            prepared.measurement,
            exact_identities=prepared.identity_map(),
        )

    def record_trace_error(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        trace_identity: Mapping[str, str | None],
        tool_call_id: str,
        latency_ms: int,
    ) -> RecordedRetrieval | None:
        """Record a fixed error outcome without accepting exception or query data."""

        measurement = measurement_from_error(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            trace_identity=trace_identity,
            tool_call_id=tool_call_id,
            latency_ms=latency_ms,
        )
        if measurement is None:
            return None
        return self.repository.record(
            measurement,
            exact_identities={},
        )

    def aggregate(
        self, *, tenant_id: str, actor_open_id: str, **kwargs: Any
    ) -> RetrievalOutcomeMetrics:
        return self.repository.aggregate(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            **kwargs,
        )


def _prepare_measurement_from_result(
    *,
    tenant_id: str,
    actor_open_id: str,
    trace_identity: Mapping[str, str | None],
    tool_call_id: str,
    latency_ms: int,
    result: Any,
) -> PreparedRetrievalMetric | None:
    """Project one tool result into the only payload allowed on the metric queue."""

    try:
        tenant_id = RetrievalMetricsRepository._required_text(tenant_id, "tenant_id")
        actor_open_id = RetrievalMetricsRepository._required_text(
            actor_open_id, "actor_open_id"
        )
    except ValueError:
        return None
    if not isinstance(result, dict):
        return None
    if is_retrieval_error_result(result):
        measurement = measurement_from_error(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            trace_identity=trace_identity,
            tool_call_id=tool_call_id,
            latency_ms=latency_ms,
        )
        if measurement is None:
            return None
        return PreparedRetrievalMetric(measurement=measurement, exact_identities=())
    if "error" in result:
        return None
    mode = result.get("retrieval_mode")
    if mode not in RETRIEVAL_MODES:
        return None
    raw_evidence = result.get("evidence")
    if not isinstance(raw_evidence, list) or len(raw_evidence) > 100:
        return None
    raw_engines = result.get("engines_used")
    if not isinstance(raw_engines, list):
        return None
    engines = _engine_set(raw_engines)
    if engines is None:
        return None
    raw_degraded = result.get("degraded_engines")
    if not isinstance(raw_degraded, list) or len(raw_degraded) > 3:
        return None
    degraded: set[str] = set()
    for item in raw_degraded:
        if not isinstance(item, dict) or item.get("engine") not in _RECALL_ENGINES:
            return None
        degraded.add(str(item["engine"]))
    if len(degraded) != len(raw_degraded) or engines.intersection(degraded):
        return None

    exposures: list[RetrievalExposure] = []
    exact_identities: dict[str, tuple[str, int]] = {}
    seen: set[tuple[str, int]] = set()
    evidence_sources: set[str] = set()
    for rank, item in enumerate(raw_evidence, start=1):
        prepared_exposure = _exposure(item, rank=rank, tenant_id=tenant_id)
        if prepared_exposure is None:
            return None
        exposure, identity = prepared_exposure
        if identity in seen:
            return None
        seen.add(identity)
        exact_identities[exposure.evidence_key] = identity
        if exposure.recalled_by_semantic:
            evidence_sources.add("semantic")
        if exposure.recalled_by_keyword:
            evidence_sources.add("keyword")
        if exposure.recalled_by_graph:
            evidence_sources.add("graph")
        exposures.append(exposure)

    if mode == "insufficient_relevance":
        if exposures:
            return None
    elif not exposures or evidence_sources != engines:
        return None
    primary = evidence_sources.intersection({"semantic", "keyword"})
    if mode == "hybrid" and primary != {"semantic", "keyword"}:
        return None
    if mode == "semantic_only" and primary != {"semantic"}:
        return None
    if mode == "keyword_only" and primary != {"keyword"}:
        return None

    run_id = trace_identity.get("run_id")
    turn_id = trace_identity.get("turn_id")
    thread_id = trace_identity.get("thread_id")
    if not isinstance(run_id, str) or not isinstance(turn_id, str):
        return None
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None
    if (
        not isinstance(latency_ms, int)
        or isinstance(latency_ms, bool)
        or latency_ms < 0
    ):
        return None
    measurement = _measurement(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        thread_id=thread_id,
        run_id=run_id,
        turn_id=turn_id,
        tool_call_id=tool_call_id,
        latency_ms=latency_ms,
        outcome="success",
        retrieval_mode=str(mode),
        engine_count=len(engines),
        degraded_engine_count=len(degraded),
        exposures=tuple(exposures),
    )
    if measurement is None:
        return None
    return PreparedRetrievalMetric(
        measurement=measurement,
        exact_identities=tuple(
            (evidence_key, resource_id, resource_version)
            for evidence_key, (resource_id, resource_version) in exact_identities.items()
        ),
    )


def measurement_from_result(
    *,
    tenant_id: str,
    actor_open_id: str,
    trace_identity: Mapping[str, str | None],
    tool_call_id: str,
    latency_ms: int,
    result: Any,
) -> RetrievalMeasurement | None:
    """Return only the safe persisted projection; exact IDs remain internal."""

    prepared = _prepare_measurement_from_result(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        trace_identity=trace_identity,
        tool_call_id=tool_call_id,
        latency_ms=latency_ms,
        result=result,
    )
    return prepared.measurement if prepared is not None else None


def measurement_from_error(
    *,
    tenant_id: str,
    actor_open_id: str,
    trace_identity: Mapping[str, str | None],
    tool_call_id: str,
    latency_ms: int,
) -> RetrievalMeasurement | None:
    """Build the only permitted error projection: identity, latency and outcome."""

    return _measurement(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        thread_id=trace_identity.get("thread_id"),
        run_id=trace_identity.get("run_id"),
        turn_id=trace_identity.get("turn_id"),
        tool_call_id=tool_call_id,
        latency_ms=latency_ms,
        outcome="error",
        retrieval_mode=None,
        engine_count=0,
        degraded_engine_count=0,
        exposures=(),
    )


def prepare_retrieval_result(
    *,
    config: Any,
    trace_identity: Mapping[str, str | None],
    tool_call_id: str,
    latency_ms: int,
    result: Any,
) -> PreparedRetrievalMetric | None:
    """Resolve runtime identity and discard the raw config/result before queuing."""

    actor_open_id = actor_from_config(config)
    return _prepare_measurement_from_result(
        tenant_id=default_tenant_id(),
        actor_open_id=actor_open_id,
        trace_identity=trace_identity,
        tool_call_id=tool_call_id,
        latency_ms=latency_ms,
        result=result,
    )


def prepare_retrieval_error(
    *,
    config: Any,
    trace_identity: Mapping[str, str | None],
    tool_call_id: str,
    latency_ms: int,
) -> PreparedRetrievalMetric | None:
    """Build an exception-path projection without accepting exception content."""

    actor_open_id = actor_from_config(config)
    measurement = measurement_from_error(
        tenant_id=default_tenant_id(),
        actor_open_id=actor_open_id,
        trace_identity=trace_identity,
        tool_call_id=tool_call_id,
        latency_ms=latency_ms,
    )
    if measurement is None:
        return None
    return PreparedRetrievalMetric(measurement=measurement, exact_identities=())


def _metric_connection() -> Any:
    return connect(
        connect_timeout=_METRIC_CONNECT_TIMEOUT_SECONDS,
        options=(
            f"-c statement_timeout={_METRIC_STATEMENT_TIMEOUT_MS} "
            f"-c lock_timeout={_METRIC_LOCK_TIMEOUT_MS}"
        ),
    )


def persist_prepared_retrieval_metric(
    prepared: PreparedRetrievalMetric,
    *,
    connection_factory: Callable[[], Any] | None = None,
) -> RecordedRetrieval:
    """Persist a pre-sanitized projection on a worker-owned short-timeout connection."""

    if not isinstance(prepared, PreparedRetrievalMetric):
        raise TypeError("prepared retrieval metric is required")
    factory = connection_factory or _metric_connection
    with factory() as connection:
        return RetrievalMetricsRepository(connection).record(
            prepared.measurement,
            exact_identities=prepared.identity_map(),
        )


def start_retrieval_metric_dispatcher() -> BoundedRetrievalMetricDispatcher:
    global _GLOBAL_DISPATCHER, _GLOBAL_DISPATCHER_CLOSED
    with _GLOBAL_DISPATCHER_LOCK:
        _GLOBAL_DISPATCHER_CLOSED = False
        if _GLOBAL_DISPATCHER is None:
            _GLOBAL_DISPATCHER = BoundedRetrievalMetricDispatcher(
                persist_prepared_retrieval_metric,
            )
        return _GLOBAL_DISPATCHER


def shutdown_retrieval_metric_dispatcher(*, wait: bool = True) -> None:
    global _GLOBAL_DISPATCHER, _GLOBAL_DISPATCHER_CLOSED
    with _GLOBAL_DISPATCHER_LOCK:
        _GLOBAL_DISPATCHER_CLOSED = True
        dispatcher = _GLOBAL_DISPATCHER
        _GLOBAL_DISPATCHER = None
    if dispatcher is not None:
        dispatcher.shutdown(wait=wait)


def _global_dispatcher() -> BoundedRetrievalMetricDispatcher | None:
    global _GLOBAL_DISPATCHER
    with _GLOBAL_DISPATCHER_LOCK:
        if _GLOBAL_DISPATCHER_CLOSED:
            return None
        if _GLOBAL_DISPATCHER is None:
            _GLOBAL_DISPATCHER = BoundedRetrievalMetricDispatcher(
                persist_prepared_retrieval_metric,
            )
        return _GLOBAL_DISPATCHER


def submit_retrieval_metric(
    prepared: PreparedRetrievalMetric,
    *,
    dispatcher: BoundedRetrievalMetricDispatcher | None = None,
) -> bool:
    """Submit without waiting; return false when the bounded queue is full/stopped."""

    selected = dispatcher or _global_dispatcher()
    return selected.submit(prepared) if selected is not None else False


def safe_metrics_payload(metrics: RetrievalOutcomeMetrics) -> dict[str, Any]:
    """Serialize aggregate numbers/fingerprints without adding flexible fields."""

    return asdict(metrics)


def _engine_set(values: list[Any]) -> set[str] | None:
    if len(values) > 3 or any(value not in _RECALL_ENGINES for value in values):
        return None
    engines = {str(value) for value in values}
    return engines if len(engines) == len(values) else None


def _exposure(
    item: Any, *, rank: int, tenant_id: str
) -> tuple[RetrievalExposure, tuple[str, int]] | None:
    if not isinstance(item, dict):
        return None
    try:
        resource_id = str(uuid.UUID(str(item.get("resource_id"))))
    except (ValueError, TypeError, AttributeError):
        return None
    resource_version = item.get("resource_version")
    if (
        not isinstance(resource_version, int)
        or isinstance(resource_version, bool)
        or resource_version <= 0
    ):
        return None
    raw_sources = item.get("retrieval_sources")
    if not isinstance(raw_sources, list):
        return None
    sources = _engine_set(raw_sources)
    if not sources:
        return None
    scores: dict[str, float] = {}
    for field in ("score", "relevance", "quality", "freshness", "performance"):
        score = _unit_float(item.get(field))
        if score is None:
            return None
        scores[field] = score
    exposure = RetrievalExposure(
        evidence_key=exact_evidence_key(tenant_id, resource_id, resource_version),
        rank=rank,
        score=scores["score"],
        relevance=scores["relevance"],
        quality=scores["quality"],
        freshness=scores["freshness"],
        performance=scores["performance"],
        recalled_by_semantic="semantic" in sources,
        recalled_by_keyword="keyword" in sources,
        recalled_by_graph="graph" in sources,
    )
    return exposure, (resource_id, resource_version)


def _unit_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0.0 <= number <= 1.0 else None


def _measurement(
    *,
    tenant_id: str,
    actor_open_id: str,
    thread_id: Any,
    run_id: Any,
    turn_id: Any,
    tool_call_id: Any,
    latency_ms: Any,
    outcome: str,
    retrieval_mode: str | None,
    engine_count: int,
    degraded_engine_count: int,
    exposures: tuple[RetrievalExposure, ...],
) -> RetrievalMeasurement | None:
    try:
        tenant_id = RetrievalMetricsRepository._required_text(tenant_id, "tenant_id")
        actor_open_id = RetrievalMetricsRepository._required_text(
            actor_open_id, "actor_open_id"
        )
    except ValueError:
        return None
    if not isinstance(run_id, str) or not run_id:
        return None
    if not isinstance(turn_id, str) or not turn_id:
        return None
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None
    if thread_id is not None and (not isinstance(thread_id, str) or not thread_id):
        return None
    if (
        not isinstance(latency_ms, int)
        or isinstance(latency_ms, bool)
        or latency_ms < 0
    ):
        return None
    # A tool-call ID can be reused by different turns during retries or malformed
    # provider callbacks. Length-prefixing makes the composite unambiguous while the
    # database still receives only its digest.
    call_identity = f"{len(turn_id)}:{turn_id}{tool_call_id}"
    return RetrievalMeasurement(
        tenant_id=tenant_id,
        actor_key=RetrievalMetricsRepository.actor_key(tenant_id, actor_open_id),
        thread_key=correlation_key(thread_id) if thread_id is not None else None,
        run_key=correlation_key(run_id),
        turn_key=correlation_key(turn_id),
        tool_call_key=correlation_key(call_identity),
        outcome=outcome,
        retrieval_mode=retrieval_mode,
        engine_count=engine_count,
        degraded_engine_count=degraded_engine_count,
        latency_ms=latency_ms,
        observed_at=datetime.now(UTC),
        exposures=exposures,
    )


__all__ = [
    "BoundedRetrievalMetricDispatcher",
    "PreparedRetrievalMetric",
    "RetrievalMetricDispatcherStats",
    "RetrievalMetricsService",
    "correlation_key",
    "measurement_from_error",
    "measurement_from_result",
    "persist_prepared_retrieval_metric",
    "prepare_retrieval_error",
    "prepare_retrieval_result",
    "safe_metrics_payload",
    "shutdown_retrieval_metric_dispatcher",
    "start_retrieval_metric_dispatcher",
    "submit_retrieval_metric",
]
