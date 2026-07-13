from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import threading
import time

import pytest

from data_foundation.repositories.retrieval_metrics import (
    RetrievalMetricsRepository,
    exact_evidence_key,
    retrieval_payload_key,
)
from data_foundation.retrieval_metrics import (
    BoundedRetrievalMetricDispatcher,
    PreparedRetrievalMetric,
    RetrievalMetricsService,
    correlation_key,
    measurement_from_error,
    measurement_from_result,
    prepare_retrieval_result,
    safe_metrics_payload,
)


EVIDENCE_ID = "11111111-1111-1111-1111-111111111111"


def _result(resource_id: str = EVIDENCE_ID) -> dict:
    return {
        "retrieval_mode": "hybrid",
        "evidence": [
            {
                "resource_id": resource_id,
                "resource_version": 3,
                "title": "不得进入指标的标题",
                "summary": "不得进入指标的摘要",
                "body": "不得进入指标的正文",
                "score": 0.9,
                "relevance": 0.8,
                "quality": 0.7,
                "freshness": 0.6,
                "performance": 0.5,
                "retrieval_sources": ["semantic", "keyword"],
            }
        ],
        "engines_used": ["semantic", "keyword"],
        "degraded_engines": [{"engine": "graph", "reason_code": "PRIVATE-SECRET"}],
        "query": "不得进入指标的查询",
        "api_key": "sk-private-secret",
    }


def _measurement(result: dict | None = None):
    return measurement_from_result(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={
            "thread_id": "thread-private",
            "run_id": "run-private",
            "turn_id": "turn-private",
        },
        tool_call_id="tool-private",
        latency_ms=37,
        result=result or _result(),
    )


def test_measurement_whitelists_fingerprints_and_numeric_signals_only() -> None:
    measurement = _measurement()
    assert measurement is not None
    serialized = str(asdict(measurement))

    for forbidden in (
        "不得进入指标",
        "private-secret",
        "ou-private-user",
        EVIDENCE_ID,
    ):
        assert forbidden not in serialized
    assert measurement.actor_key == RetrievalMetricsRepository.actor_key(
        "tenant-a", "ou-private-user"
    )
    assert measurement.exposures[0].evidence_key == exact_evidence_key(
        "tenant-a", EVIDENCE_ID, 3
    )
    assert measurement.latency_ms == 37
    assert measurement.outcome == "success"
    assert measurement.observed_at.tzinfo is not None


def test_measurement_rejects_non_exact_or_mode_inconsistent_results() -> None:
    assert _measurement(_result("not-a-uuid")) is None
    inconsistent = _result()
    inconsistent["retrieval_mode"] = "semantic_only"
    assert _measurement(inconsistent) is None
    duplicate = _result()
    duplicate["evidence"] = duplicate["evidence"] * 2
    assert _measurement(duplicate) is None


def test_insufficient_relevance_is_recorded_without_content_or_evidence() -> None:
    measurement = _measurement(
        {
            "retrieval_mode": "insufficient_relevance",
            "evidence": [],
            "engines_used": [],
            "degraded_engines": [],
            "gaps": "不得保存的内容缺口说明",
        }
    )
    assert measurement is not None
    assert measurement.exposures == ()
    assert "不得保存" not in str(asdict(measurement))


def test_error_measurement_is_a_fixed_whitelist_without_error_or_query() -> None:
    measurement = measurement_from_error(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={
            "thread_id": "thread-private",
            "run_id": "run-private",
            "turn_id": "turn-private",
        },
        tool_call_id="tool-private",
        latency_ms=41,
    )
    assert measurement is not None
    serialized = asdict(measurement)
    assert serialized["outcome"] == "error"
    assert serialized["retrieval_mode"] is None
    assert serialized["engine_count"] == 0
    assert serialized["degraded_engine_count"] == 0
    assert serialized["exposures"] == ()
    assert not {"query", "error", "exception", "message", "provider"}.intersection(
        serialized
    )


def test_returned_tool_error_is_counted_without_persisting_error_content() -> None:
    measurement = _measurement({"error": "KNOWLEDGE_RETRIEVAL_FAILED"})
    assert measurement is not None
    assert measurement.outcome == "error"
    assert measurement.retrieval_mode is None
    assert "KNOWLEDGE_RETRIEVAL_FAILED" not in str(asdict(measurement))

    for malformed in (
        {"error": None},
        {"error": []},
        {"error": "UNKNOWN_RETRIEVAL_ERROR"},
        {"error": "KNOWLEDGE_RETRIEVAL_FAILED", "query": "private query"},
    ):
        assert _measurement(malformed) is None


def test_prepared_queue_payload_discards_config_actor_and_raw_result() -> None:
    prepared = prepare_retrieval_result(
        config={
            "configurable": {
                "langgraph_auth_user": {"identity": "ou-private-user"}
            }
        },
        trace_identity={
            "thread_id": "thread-private",
            "run_id": "run-private",
            "turn_id": "turn-private",
        },
        tool_call_id="tool-private",
        latency_ms=5,
        result=_result(),
    )
    assert prepared is not None
    serialized = str(asdict(prepared))
    for forbidden in (
        "ou-private-user",
        "private-secret",
        "不得进入指标",
        "langgraph_auth_user",
        "query",
        "title",
        "body",
        "config",
    ):
        assert forbidden not in serialized
    assert prepared.exact_identities == (
        (prepared.measurement.exposures[0].evidence_key, EVIDENCE_ID, 3),
    )


def test_correlation_and_exact_keys_are_stable_and_tenant_scoped() -> None:
    assert correlation_key("turn-1") == correlation_key("turn-1")
    assert correlation_key("turn-1") != correlation_key("turn-2")
    assert exact_evidence_key("tenant-a", EVIDENCE_ID, 1) != exact_evidence_key(
        "tenant-b", EVIDENCE_ID, 1
    )
    assert exact_evidence_key("tenant-a", EVIDENCE_ID, 1) != exact_evidence_key(
        "tenant-a", EVIDENCE_ID, 2
    )
    with pytest.raises(ValueError, match="actor_open_id"):
        RetrievalMetricsRepository.actor_key("tenant-a", " ")
    assert measurement_from_error(
        tenant_id="tenant-a",
        actor_open_id=" ",
        trace_identity={"thread_id": None, "run_id": "r", "turn_id": "t"},
        tool_call_id="call",
        latency_ms=1,
    ) is None


def test_tool_call_idempotency_is_scoped_to_turn() -> None:
    first = _measurement()
    replay = _measurement()
    cross_turn = measurement_from_result(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={
            "thread_id": "thread-private",
            "run_id": "run-private-2",
            "turn_id": "turn-private-2",
        },
        tool_call_id="tool-private",
        latency_ms=37,
        result=_result(),
    )
    assert first is not None and replay is not None and cross_turn is not None
    assert first.tool_call_key == replay.tool_call_key
    assert first.tool_call_key != cross_turn.tool_call_key


def test_replay_payload_fingerprint_covers_full_projection_but_not_timing() -> None:
    measurement = _measurement()
    assert measurement is not None
    assert retrieval_payload_key(measurement) == retrieval_payload_key(
        replace(
            measurement,
            latency_ms=999,
            observed_at=measurement.observed_at + timedelta(seconds=5),
        )
    )
    assert retrieval_payload_key(measurement) != retrieval_payload_key(
        replace(
            measurement,
            exposures=(replace(measurement.exposures[0], score=0.123),),
        )
    )


def test_aggregate_sql_uses_persistent_identity_map_not_version_digest_scan() -> None:
    sql = RetrievalMetricsRepository(None)._aggregate_ctes("")  # type: ignore[arg-type]
    assert "join knowledge_retrieval_evidence_keys identity" in sql
    assert "join resource_versions evidence_version" not in sql
    assert "concat_ws" not in sql
    assert sql.count("and event.created_at <= %(as_of)s") == 3


def test_actor_key_acl_uses_the_shared_acl_rules_and_rejects_null_owner() -> None:
    from data_foundation.permissions import readable_resource_by_actor_key_where

    sql = readable_resource_by_actor_key_where("evidence_resource")
    assert "evidence_resource.owner_open_id is not null" in sql
    assert "evidence_resource.visibility = 'team'" in sql
    assert "rp.subject_type = 'user'" in sql
    assert "rp.permission in ('read', 'write', 'admin')" in sql
    assert sql.count("%(actor_key)s") == 2


def test_service_discards_raw_actor_before_repository_boundary() -> None:
    calls = []

    class Repository:
        def record(self, measurement, *, exact_identities):
            calls.append((measurement, exact_identities))
            return "recorded"

    service = RetrievalMetricsService(Repository())  # type: ignore[arg-type]
    recorded = service.record_trace_result(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={"thread_id": None, "run_id": "r", "turn_id": "t"},
        tool_call_id="call",
        latency_ms=2,
        result=_result(),
    )
    assert recorded == "recorded"
    assert "ou-private-user" not in str(asdict(calls[0][0]))
    assert calls[0][1]


def test_service_error_path_has_no_error_payload_parameter() -> None:
    calls = []

    class Repository:
        def record(self, measurement, *, exact_identities):
            calls.append((measurement, exact_identities))
            return "recorded"

    service = RetrievalMetricsService(Repository())  # type: ignore[arg-type]
    recorded = service.record_trace_error(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={"thread_id": None, "run_id": "r", "turn_id": "t"},
        tool_call_id="call",
        latency_ms=2,
    )
    assert recorded == "recorded"
    assert calls[0][0].outcome == "error"
    assert calls[0][1] == {}


def test_bounded_dispatcher_never_waits_when_capacity_is_full() -> None:
    started = threading.Event()
    release = threading.Event()
    measurement = measurement_from_error(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={"thread_id": None, "run_id": "r", "turn_id": "t"},
        tool_call_id="call",
        latency_ms=2,
    )
    assert measurement is not None
    prepared = PreparedRetrievalMetric(measurement=measurement, exact_identities=())

    def blocking_writer(_prepared):
        started.set()
        assert release.wait(timeout=2)

    dispatcher = BoundedRetrievalMetricDispatcher(
        blocking_writer,
        max_workers=1,
        max_in_flight=1,
    )
    try:
        assert dispatcher.submit(prepared) is True
        assert started.wait(timeout=1)
        began = time.perf_counter()
        assert dispatcher.submit(prepared) is False
        assert time.perf_counter() - began < 0.1
        assert dispatcher.stats().accepted == 1
        assert dispatcher.stats().dropped == 1
    finally:
        release.set()
        dispatcher.shutdown()
    assert dispatcher.submit(prepared) is False
    assert dispatcher.stats().dropped == 2


def test_background_writer_failure_logs_only_exception_class(caplog) -> None:
    secret = "token=background-private-secret"
    measurement = measurement_from_error(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={"thread_id": None, "run_id": "r", "turn_id": "t"},
        tool_call_id="call",
        latency_ms=2,
    )
    assert measurement is not None
    prepared = PreparedRetrievalMetric(measurement=measurement, exact_identities=())

    def failing_writer(_prepared):
        raise RuntimeError(secret)

    dispatcher = BoundedRetrievalMetricDispatcher(
        failing_writer,
        max_workers=1,
        max_in_flight=5,
    )
    for _ in range(5):
        dispatcher._write_safely(prepared)
    dispatcher.shutdown()
    assert dispatcher.stats().write_failed == 5
    assert caplog.text.count("retrieval metric background writes failed") == 3
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


def test_global_dispatcher_lifecycle_stops_recreation_after_shutdown(
    monkeypatch,
) -> None:
    import data_foundation.retrieval_metrics as metrics_module

    calls = []

    class FakeDispatcher:
        def submit(self, _prepared):
            calls.append("submit")
            return True

        def shutdown(self, *, wait):
            calls.append(("shutdown", wait))

    fake = FakeDispatcher()
    monkeypatch.setattr(metrics_module, "_GLOBAL_DISPATCHER", None)
    monkeypatch.setattr(metrics_module, "_GLOBAL_DISPATCHER_CLOSED", False)
    monkeypatch.setattr(
        metrics_module,
        "BoundedRetrievalMetricDispatcher",
        lambda _writer: fake,
    )
    assert metrics_module.start_retrieval_metric_dispatcher() is fake
    metrics_module.shutdown_retrieval_metric_dispatcher(wait=False)
    assert calls == [("shutdown", False)]

    measurement = measurement_from_error(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={"thread_id": None, "run_id": "r", "turn_id": "t"},
        tool_call_id="call",
        latency_ms=2,
    )
    assert measurement is not None
    prepared = PreparedRetrievalMetric(measurement=measurement, exact_identities=())
    assert metrics_module.submit_retrieval_metric(prepared) is False
    assert calls == [("shutdown", False)]


def test_dispatcher_shutdown_cancels_queued_measurements() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    writes = []
    measurement = measurement_from_error(
        tenant_id="tenant-a",
        actor_open_id="ou-private-user",
        trace_identity={"thread_id": None, "run_id": "r", "turn_id": "t"},
        tool_call_id="call",
        latency_ms=2,
    )
    assert measurement is not None
    prepared = PreparedRetrievalMetric(measurement=measurement, exact_identities=())

    def blocking_writer(_prepared):
        writes.append("started")
        started.set()
        assert release.wait(timeout=2)
        finished.set()

    dispatcher = BoundedRetrievalMetricDispatcher(
        blocking_writer,
        max_workers=1,
        max_in_flight=3,
    )
    for _ in range(3):
        assert dispatcher.submit(prepared) is True
    assert started.wait(timeout=1)
    dispatcher.shutdown(wait=False)
    release.set()
    assert finished.wait(timeout=1)
    assert writes == ["started"]


def test_metric_connection_enforces_short_connect_statement_and_lock_timeouts(
    monkeypatch,
) -> None:
    import data_foundation.retrieval_metrics as metrics_module

    captured = {}
    connection = object()

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(metrics_module, "connect", fake_connect)
    assert metrics_module._metric_connection() is connection
    assert 0 < captured["connect_timeout"] <= 2
    assert "statement_timeout=2000" in captured["options"]
    assert "lock_timeout=500" in captured["options"]


def test_retention_rejects_unbounded_or_naive_requests_before_database_access() -> None:
    repo = RetrievalMetricsRepository(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone"):
        repo.delete_expired(older_than=datetime.now(), limit=10)
    with pytest.raises(ValueError, match="between 1 and 10000"):
        repo.delete_expired(older_than=datetime.now(UTC), limit=0)
    measurement = _measurement()
    assert measurement is not None
    with pytest.raises(ValueError, match="future"):
        repo._validate_measurement(
            replace(measurement, observed_at=datetime.now(UTC) + timedelta(hours=1))
        )


def test_schema_has_no_content_open_id_or_resource_identity_metric_columns() -> None:
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()
    runs = schema.split("create table if not exists knowledge_retrieval_runs", 1)[1].split(
        "create index if not exists idx_knowledge_retrieval_runs_actor_recent", 1
    )[0]
    exposures = schema.split(
        "create table if not exists knowledge_retrieval_exposures", 1
    )[1].split("create index if not exists idx_knowledge_retrieval_exposures", 1)[0]
    for forbidden in (
        "query",
        "title",
        "summary",
        "content",
        "open_id",
        "resource_id",
        "resource_version",
        "jsonb",
    ):
        assert forbidden not in runs
        assert forbidden not in exposures
    assert "actor_key char(64)" in runs
    assert "payload_key char(64)" in runs
    assert "evidence_key char(64)" in exposures
    assert "knowledge_retrieval_evidence_keys" in schema
    assert "foreign key (tenant_id, evidence_key)" in exposures
    assert "idx_knowledge_retrieval_runs_retention" in schema
    assert "on knowledge_retrieval_runs (created_at, id)" in schema
    assert "idx_knowledge_retrieval_exposures_run" in schema
    assert "on knowledge_retrieval_exposures (retrieval_run_id, evidence_key)" in schema


def test_safe_metrics_payload_never_adds_flexible_data() -> None:
    from data_foundation.repositories.retrieval_metrics import RetrievalOutcomeMetrics

    metrics = RetrievalOutcomeMetrics(
        retrieval_run_count=2,
        successful_run_count=1,
        error_run_count=1,
        hybrid_run_count=1,
        semantic_only_run_count=0,
        keyword_only_run_count=0,
        insufficient_relevance_run_count=0,
        error_rate=0.5,
        degraded_run_count=1,
        degraded_run_rate=1.0,
        latency_p50_ms=10,
        latency_p95_ms=20,
        latency_p99_ms=20,
        evidence_exposure_count=3,
        unique_evidence_exposure_count=3,
        attributed_copy_count=1,
        mature_explicit_copy_count=0,
        explicit_adopted_copy_count=None,
        censored_explicit_copy_count=1,
        mature_committed_copy_count=0,
        committed_use_copy_count=None,
        censored_committed_copy_count=1,
        published_copy_count=None,
        explicit_adoption_rate=None,
        committed_use_rate=None,
        sample_suppressed=True,
    )
    payload = safe_metrics_payload(metrics)
    assert payload["sample_suppressed"] is True
    assert not {"query", "title", "summary", "content", "open_id", "resource_id"}.intersection(
        payload
    )
    assert "evidence" not in payload


def test_deepagents_trace_hook_records_only_unified_retrieval(monkeypatch) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    captured = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "data_foundation.retrieval_metrics.submit_retrieval_metric",
        lambda prepared: captured.append(prepared) or True,
    )

    @tool("retrieve_knowledge")
    def retrieve(query: str, config: dict | None = None) -> dict:
        """Return unified evidence."""

        return _result()

    wrapped = trace_tool(retrieve, stage_id="retrieve", label="检索知识库")
    returned = wrapped.func(
        "不得落库的查询",
        config={
            "configurable": {
                "run_id": "run",
                "turn_id": "turn",
                "langgraph_auth_user": {"identity": "ou-user"},
            }
        },
    )
    assert returned == _result()
    assert len(captured) == 1
    assert isinstance(captured[0], PreparedRetrievalMetric)
    assert captured[0].measurement.latency_ms >= 0
    assert captured[0].measurement.outcome == "success"


def test_deepagents_trace_hook_counts_returned_error_as_error(monkeypatch) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    captured = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "data_foundation.retrieval_metrics.submit_retrieval_metric",
        lambda prepared: captured.append(prepared) or True,
    )

    @tool("retrieve_knowledge")
    def retrieve(query: str, config: dict | None = None) -> dict:
        """Return a handled retrieval failure."""

        return {"error": "KNOWLEDGE_RETRIEVAL_FAILED"}

    returned = trace_tool(retrieve, stage_id="retrieve", label="retrieve").func(
        "private query",
        config={
            "configurable": {
                "run_id": "run",
                "turn_id": "turn",
                "langgraph_auth_user": {"identity": "ou-user"},
            }
        },
    )
    assert returned["error"] == "KNOWLEDGE_RETRIEVAL_FAILED"
    assert len(captured) == 1
    assert captured[0].measurement.outcome == "error"
    assert "KNOWLEDGE_RETRIEVAL_FAILED" not in str(asdict(captured[0]))


def test_trace_stream_failure_does_not_skip_success_or_error_metrics(
    monkeypatch, caplog
) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    secret = "token=stream-private"
    captured = []

    def failing_writer(_event):
        raise RuntimeError(secret)

    monkeypatch.setattr(
        "data_foundation.agent_trace.get_stream_writer",
        lambda: failing_writer,
    )
    monkeypatch.setattr(
        "data_foundation.retrieval_metrics.submit_retrieval_metric",
        lambda prepared: captured.append(prepared) or True,
    )
    config = {
        "configurable": {
            "run_id": "run",
            "turn_id": "turn",
            "langgraph_auth_user": {"identity": "ou-user"},
        }
    }

    @tool("retrieve_knowledge")
    def successful(query: str, config: dict | None = None) -> dict:
        """Return unified evidence."""

        return _result()

    assert trace_tool(successful, stage_id="retrieve", label="retrieve").func(
        "private query", config=config
    ) == _result()

    original = RuntimeError("private provider response")

    @tool("retrieve_knowledge")
    def failing(query: str, config: dict | None = None) -> dict:
        """Raise a retrieval failure."""

        raise original

    with pytest.raises(RuntimeError) as raised:
        trace_tool(failing, stage_id="retrieve", label="retrieve").func(
            "private query", config=config
        )
    assert raised.value is original
    assert [item.measurement.outcome for item in captured] == ["success", "error"]
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


def test_deepagents_error_hook_records_fixed_outcome_and_reraises(monkeypatch) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    captured = []
    original_error = RuntimeError("private provider response")
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "data_foundation.retrieval_metrics.submit_retrieval_metric",
        lambda prepared: captured.append(prepared) or True,
    )

    @tool("retrieve_knowledge")
    def retrieve(query: str, config: dict | None = None) -> dict:
        """Fail retrieval."""

        raise original_error

    wrapped = trace_tool(retrieve, stage_id="retrieve", label="retrieve")
    with pytest.raises(RuntimeError) as raised:
        wrapped.func(
            "private query",
            config={
                "configurable": {
                    "run_id": "run",
                    "turn_id": "turn",
                    "langgraph_auth_user": {"identity": "ou-user"},
                }
            },
            xhs_trace_tool_call_id="call-real",
        )
    assert raised.value is original_error
    assert len(captured) == 1
    assert captured[0].measurement.outcome == "error"
    assert captured[0].measurement.exposures == ()


def test_metric_capture_failure_does_not_break_retrieval_or_log_secret(
    monkeypatch, caplog
) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    secret = "dsn-private-secret"
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda *_args, **_kwargs: None)

    def fail(_prepared):
        raise RuntimeError(secret)

    monkeypatch.setattr(
        "data_foundation.retrieval_metrics.submit_retrieval_metric", fail
    )

    @tool("retrieve_knowledge")
    def retrieve(query: str, config: dict | None = None) -> dict:
        """Return unified evidence."""

        return _result()

    returned = trace_tool(retrieve, stage_id="retrieve", label="检索知识库").func(
        "query",
        config={
            "configurable": {
                "run_id": "run",
                "turn_id": "turn",
                "langgraph_auth_user": {"identity": "ou-user"},
            }
        },
    )
    assert returned == _result()
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


def _qualify(repo, *, tenant_id: str, actor: str, visibility: str = "team"):
    from data_foundation.knowledge.service import KnowledgeService

    resource = repo.upsert_resource(
        tenant_id=tenant_id,
        actor_open_id=actor,
        resource_type="xhs_online_note",
        title="基准素材",
        content_text="足够长的基准素材正文用于知识资格测试",
        content_json={"quality_score": 0.9},
        visibility=visibility,
        owner_open_id=actor,
        outbox_requests=[],
    )
    KnowledgeService(repo.conn).enrich_exact_version(
        tenant_id=tenant_id,
        resource_id=resource.id,
        resource_version=int(resource.version),
    )
    return resource


def _db_result(evidence) -> dict:
    result = _result(evidence.id)
    result["evidence"][0]["resource_version"] = int(evidence.version)
    return result


def _record(metrics_repo, *, tenant_id: str, actor: str, evidence, turn: str, call: str):
    return RetrievalMetricsService(metrics_repo).record_trace_result(
        tenant_id=tenant_id,
        actor_open_id=actor,
        trace_identity={"thread_id": "thread", "run_id": call, "turn_id": turn},
        tool_call_id=call,
        latency_ms=10,
        result=_db_result(evidence),
    )


def test_aggregate_reports_modes_errors_degradation_and_latency(migrated_conn) -> None:
    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-operational-metrics"
    actor = "ou-owner"
    evidence = _qualify(
        ResourceRepository(migrated_conn), tenant_id=tenant, actor=actor
    )
    metrics_repo = RetrievalMetricsRepository(migrated_conn)
    service = RetrievalMetricsService(metrics_repo)

    hybrid = _db_result(evidence)
    semantic = _db_result(evidence)
    semantic["retrieval_mode"] = "semantic_only"
    semantic["evidence"][0]["retrieval_sources"] = ["semantic"]
    semantic["engines_used"] = ["semantic"]
    semantic["degraded_engines"] = []
    keyword = _db_result(evidence)
    keyword["retrieval_mode"] = "keyword_only"
    keyword["evidence"][0]["retrieval_sources"] = ["keyword"]
    keyword["engines_used"] = ["keyword"]
    keyword["degraded_engines"] = []
    insufficient = {
        "retrieval_mode": "insufficient_relevance",
        "evidence": [],
        "engines_used": [],
        "degraded_engines": [],
    }
    for index, (payload, latency) in enumerate(
        ((hybrid, 10), (semantic, 20), (keyword, 30), (insufficient, 40)),
        start=1,
    ):
        assert service.record_trace_result(
            tenant_id=tenant,
            actor_open_id=actor,
            trace_identity={
                "thread_id": "thread",
                "run_id": f"run-{index}",
                "turn_id": f"turn-{index}",
            },
            tool_call_id=f"call-{index}",
            latency_ms=latency,
            result=payload,
        ) is not None
    assert service.record_trace_error(
        tenant_id=tenant,
        actor_open_id=actor,
        trace_identity={
            "thread_id": "thread",
            "run_id": "run-error",
            "turn_id": "turn-error",
        },
        tool_call_id="call-error",
        latency_ms=50,
    ) is not None

    metrics = metrics_repo.aggregate(
        tenant_id=tenant,
        actor_open_id=actor,
        as_of=datetime.now(UTC) + timedelta(seconds=1),
        min_sample_size=1,
    )
    assert metrics.retrieval_run_count == 5
    assert metrics.successful_run_count == 4
    assert metrics.error_run_count == 1
    assert metrics.hybrid_run_count == 1
    assert metrics.semantic_only_run_count == 1
    assert metrics.keyword_only_run_count == 1
    assert metrics.insufficient_relevance_run_count == 1
    assert metrics.error_rate == 0.2
    assert metrics.degraded_run_count == 1
    assert metrics.degraded_run_rate == 0.25
    assert metrics.latency_p50_ms == 30
    assert metrics.latency_p95_ms == 50
    assert metrics.latency_p99_ms == 50


def test_idempotency_and_aggregation_are_actor_and_tenant_scoped(migrated_conn) -> None:
    service = RetrievalMetricsService(RetrievalMetricsRepository(migrated_conn))

    def record(tenant: str, actor: str, turn: str):
        return service.record_trace_error(
            tenant_id=tenant,
            actor_open_id=actor,
            trace_identity={
                "thread_id": "shared-thread",
                "run_id": f"run-{tenant}-{actor}-{turn}",
                "turn_id": turn,
            },
            tool_call_id="shared-call",
            latency_ms=7,
        )

    first = record("tenant-a", "ou-a", "turn-1")
    replay = record("tenant-a", "ou-a", "turn-1")
    cross_turn = record("tenant-a", "ou-a", "turn-2")
    cross_actor = record("tenant-a", "ou-b", "turn-1")
    cross_tenant = record("tenant-b", "ou-a", "turn-1")
    assert first is not None and replay is not None
    assert first.inserted is True and replay.inserted is False
    assert cross_turn is not None and cross_turn.inserted is True
    assert cross_actor is not None and cross_actor.inserted is True
    assert cross_tenant is not None and cross_tenant.inserted is True

    repo = RetrievalMetricsRepository(migrated_conn)
    assert repo.aggregate(
        tenant_id="tenant-a", actor_open_id="ou-a", min_sample_size=1
    ).retrieval_run_count == 2
    assert repo.aggregate(
        tenant_id="tenant-a", actor_open_id="ou-b", min_sample_size=1
    ).retrieval_run_count == 1
    assert repo.aggregate(
        tenant_id="tenant-b", actor_open_id="ou-a", min_sample_size=1
    ).retrieval_run_count == 1


def test_record_regates_exact_identity_tenant_acl_and_is_idempotent(migrated_conn) -> None:
    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-metrics"
    actor = "用户:owner"
    repo = ResourceRepository(migrated_conn)
    private_owner = _qualify(
        repo, tenant_id=tenant, actor=actor, visibility="private"
    )
    team_other = _qualify(repo, tenant_id=tenant, actor="ou-team-owner")
    private_granted = _qualify(
        repo,
        tenant_id=tenant,
        actor="ou-grant-owner",
        visibility="private",
    )
    repo.grant_permission(
        tenant_id=tenant,
        resource_id=private_granted.id,
        subject_type="user",
        subject_id=actor,
        permission="read",
    )
    private_other = _qualify(
        repo, tenant_id=tenant, actor="ou-other", visibility="private"
    )
    cross_tenant = _qualify(repo, tenant_id="tenant-other", actor=actor)
    metrics_repo = RetrievalMetricsRepository(migrated_conn)
    result = _db_result(private_owner)
    for resource in (team_other, private_granted, private_other, cross_tenant):
        result["evidence"].append(_db_result(resource)["evidence"][0])
    service = RetrievalMetricsService(metrics_repo)
    trace_identity = {"thread_id": "thread", "run_id": "call-acl", "turn_id": "turn-acl"}
    first = service.record_trace_result(
        tenant_id=tenant,
        actor_open_id=actor,
        trace_identity=trace_identity,
        tool_call_id="call-acl",
        latency_ms=10,
        result=result,
    )
    second = service.record_trace_result(
        tenant_id=tenant,
        actor_open_id=actor,
        trace_identity=trace_identity,
        tool_call_id="call-acl",
        latency_ms=10,
        result=result,
    )
    assert first is not None and second is not None
    assert (first.evidence_count, first.inserted) == (3, True)
    assert (second.evidence_count, second.inserted) == (3, False)
    stored = migrated_conn.execute(
        "select * from knowledge_retrieval_exposures where tenant_id = %s", (tenant,)
    ).fetchall()
    assert {row["evidence_key"] for row in stored} == {
        exact_evidence_key(tenant, resource.id, int(resource.version))
        for resource in (private_owner, team_other, private_granted)
    }
    mappings = migrated_conn.execute(
        "select * from knowledge_retrieval_evidence_keys where tenant_id = %s",
        (tenant,),
    ).fetchall()
    assert {
        (str(row["resource_id"]), int(row["resource_version"])) for row in mappings
    } == {
        (resource.id, int(resource.version))
        for resource in (private_owner, team_other, private_granted)
    }


def test_persisted_run_and_exposure_keep_capture_time_when_writer_is_delayed(
    migrated_conn,
) -> None:
    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-observed-at"
    actor = "ou-owner"
    evidence = _qualify(
        ResourceRepository(migrated_conn), tenant_id=tenant, actor=actor
    )
    measurement = measurement_from_result(
        tenant_id=tenant,
        actor_open_id=actor,
        trace_identity={
            "thread_id": "thread-observed",
            "run_id": "run-observed",
            "turn_id": "turn-observed",
        },
        tool_call_id="call-observed",
        latency_ms=10,
        result=_db_result(evidence),
    )
    assert measurement is not None
    observed_at = datetime.now(UTC) - timedelta(hours=1)
    measurement = replace(measurement, observed_at=observed_at)
    recorded = RetrievalMetricsRepository(migrated_conn).record(
        measurement,
        exact_identities={
            measurement.exposures[0].evidence_key: (
                evidence.id,
                int(evidence.version),
            )
        },
    )
    earlier_at = observed_at - timedelta(hours=1)
    replay = RetrievalMetricsRepository(migrated_conn).record(
        replace(measurement, observed_at=earlier_at),
        exact_identities={
            measurement.exposures[0].evidence_key: (
                evidence.id,
                int(evidence.version),
            )
        },
    )
    assert replay.inserted is False
    conflicting = replace(
        measurement,
        observed_at=earlier_at - timedelta(hours=1),
        exposures=(replace(measurement.exposures[0], score=0.123),),
    )
    with pytest.raises(ValueError, match="conflicting retrieval measurement replay"):
        RetrievalMetricsRepository(migrated_conn).record(
            conflicting,
            exact_identities={
                conflicting.exposures[0].evidence_key: (
                    evidence.id,
                    int(evidence.version),
                )
            },
        )
    timestamps = migrated_conn.execute(
        """
        select run.created_at as run_at, exposure.created_at as exposure_at
        from knowledge_retrieval_runs run
        join knowledge_retrieval_exposures exposure
          on exposure.tenant_id = run.tenant_id
         and exposure.retrieval_run_id = run.id
        where run.id = %s
        """,
        (recorded.retrieval_run_id,),
    ).fetchone()
    assert timestamps["run_at"] == earlier_at
    assert timestamps["exposure_at"] == earlier_at


def test_retention_deletes_bounded_runs_and_only_their_orphan_identity_keys(
    migrated_conn,
) -> None:
    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-retention"
    actor = "ou-owner"
    resource_repo = ResourceRepository(migrated_conn)
    shared = _qualify(resource_repo, tenant_id=tenant, actor=actor)
    old_only = _qualify(resource_repo, tenant_id=tenant, actor=actor)
    metrics_repo = RetrievalMetricsRepository(migrated_conn)
    oldest = _record(
        metrics_repo,
        tenant_id=tenant,
        actor=actor,
        evidence=shared,
        turn="turn-oldest",
        call="call-oldest",
    )
    second_old = _record(
        metrics_repo,
        tenant_id=tenant,
        actor=actor,
        evidence=old_only,
        turn="turn-second-old",
        call="call-second-old",
    )
    fresh = _record(
        metrics_repo,
        tenant_id=tenant,
        actor=actor,
        evidence=shared,
        turn="turn-fresh",
        call="call-fresh",
    )
    assert oldest is not None and second_old is not None and fresh is not None
    now = datetime.now(UTC)
    migrated_conn.execute(
        "update knowledge_retrieval_runs set created_at = %s where id = %s",
        (now - timedelta(days=120), oldest.retrieval_run_id),
    )
    migrated_conn.execute(
        "update knowledge_retrieval_runs set created_at = %s where id = %s",
        (now - timedelta(days=110), second_old.retrieval_run_id),
    )

    assert metrics_repo.delete_expired(
        older_than=now - timedelta(days=90), limit=1
    ) == 1
    remaining_runs = migrated_conn.execute(
        "select id::text from knowledge_retrieval_runs where tenant_id = %s",
        (tenant,),
    ).fetchall()
    assert {row["id"] for row in remaining_runs} == {
        second_old.retrieval_run_id,
        fresh.retrieval_run_id,
    }
    shared_key = exact_evidence_key(tenant, shared.id, int(shared.version))
    assert migrated_conn.execute(
        """
        select 1 from knowledge_retrieval_evidence_keys
        where tenant_id = %s and evidence_key = %s
        """,
        (tenant, shared_key),
    ).fetchone() is not None

    assert metrics_repo.delete_expired(
        older_than=now - timedelta(days=90), limit=10
    ) == 1
    old_only_key = exact_evidence_key(tenant, old_only.id, int(old_only.version))
    assert migrated_conn.execute(
        """
        select 1 from knowledge_retrieval_evidence_keys
        where tenant_id = %s and evidence_key = %s
        """,
        (tenant, old_only_key),
    ).fetchone() is None
    assert migrated_conn.execute(
        "select count(*) as count from knowledge_retrieval_runs where tenant_id = %s",
        (tenant,),
    ).fetchone()["count"] == 1


def test_retention_skips_writer_locked_key_then_preserves_fresh_exposure(
    migrated_conn,
    database_url,
) -> None:
    import uuid

    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-retention-writer-race"
    actor = "ou-owner"
    resource_repo = ResourceRepository(migrated_conn)
    evidence = _qualify(resource_repo, tenant_id=tenant, actor=actor)
    metrics_repo = RetrievalMetricsRepository(migrated_conn)
    old_run = _record(
        metrics_repo,
        tenant_id=tenant,
        actor=actor,
        evidence=evidence,
        turn="turn-old",
        call="call-old",
    )
    assert old_run is not None
    cutoff = datetime.now(UTC) - timedelta(days=90)
    migrated_conn.execute(
        "update knowledge_retrieval_runs set created_at = %s where id = %s",
        (cutoff - timedelta(days=1), old_run.retrieval_run_id),
    )
    schema = migrated_conn.execute(
        "select current_schema() as schema"
    ).fetchone()["schema"]
    migrated_conn.commit()

    fresh = measurement_from_result(
        tenant_id=tenant,
        actor_open_id=actor,
        trace_identity={
            "thread_id": "thread-fresh",
            "run_id": "run-fresh",
            "turn_id": "turn-fresh",
        },
        tool_call_id="call-fresh",
        latency_ms=5,
        result=_db_result(evidence),
    )
    assert fresh is not None
    exposure = fresh.exposures[0]
    fresh_run_id = str(uuid.uuid4())
    with psycopg.connect(database_url, row_factory=dict_row) as writer:
        writer.execute(
            sql.SQL("set search_path to {}, public").format(sql.Identifier(schema))
        )
        writer.execute(
            """
            update knowledge_retrieval_evidence_keys
            set last_verified_at = now()
            where tenant_id = %s and evidence_key = %s
            """,
            (tenant, exposure.evidence_key),
        )
        writer.execute(
            """
            insert into knowledge_retrieval_runs (
              id, tenant_id, actor_key, thread_key, run_key, turn_key,
              tool_call_key, payload_key, outcome, retrieval_mode,
              evidence_count, engine_count, degraded_engine_count,
              latency_ms, created_at
            ) values (
              %s, %s, %s, %s, %s, %s, %s, %s, 'success', 'hybrid',
              1, 2, 1, 5, now()
            )
            """,
            (
                fresh_run_id,
                tenant,
                fresh.actor_key,
                fresh.thread_key,
                fresh.run_key,
                fresh.turn_key,
                fresh.tool_call_key,
                retrieval_payload_key(fresh),
            ),
        )
        writer.execute(
            """
            insert into knowledge_retrieval_exposures (
              tenant_id, retrieval_run_id, evidence_key, rank,
              score, relevance, quality, freshness, performance,
              recalled_by_semantic, recalled_by_keyword,
              recalled_by_graph, created_at
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, true, true, false, now())
            """,
            (
                tenant,
                fresh_run_id,
                exposure.evidence_key,
                exposure.rank,
                exposure.score,
                exposure.relevance,
                exposure.quality,
                exposure.freshness,
                exposure.performance,
            ),
        )

        began = time.perf_counter()
        assert metrics_repo.delete_expired(older_than=cutoff, limit=10) == 0
        assert time.perf_counter() - began < 1.0
        writer.commit()

    assert metrics_repo.delete_expired(older_than=cutoff, limit=10) == 1
    assert migrated_conn.execute(
        """
        select count(*) as count
        from knowledge_retrieval_exposures
        where tenant_id = %s and retrieval_run_id = %s
        """,
        (tenant, fresh_run_id),
    ).fetchone()["count"] == 1
    assert migrated_conn.execute(
        """
        select 1 from knowledge_retrieval_evidence_keys
        where tenant_id = %s and evidence_key = %s
        """,
        (tenant, exposure.evidence_key),
    ).fetchone() is not None


def test_reverse_rank_workers_use_fixed_evidence_lock_order(
    migrated_conn,
    database_url,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-fixed-lock-order"
    actor = "ou-owner"
    resource_repo = ResourceRepository(migrated_conn)
    first = _qualify(resource_repo, tenant_id=tenant, actor=actor)
    second = _qualify(resource_repo, tenant_id=tenant, actor=actor)
    schema = migrated_conn.execute(
        "select current_schema() as schema"
    ).fetchone()["schema"]
    migrated_conn.commit()

    first_result = _db_result(first)
    first_result["evidence"].append(_db_result(second)["evidence"][0])
    second_result = _db_result(second)
    second_result["evidence"].append(_db_result(first)["evidence"][0])
    measurements = [
        measurement_from_result(
            tenant_id=tenant,
            actor_open_id=actor,
            trace_identity={
                "thread_id": "thread-lock-order",
                "run_id": f"run-lock-{index}",
                "turn_id": f"turn-lock-{index}",
            },
            tool_call_id=f"call-lock-{index}",
            latency_ms=5,
            result=result,
        )
        for index, result in enumerate((first_result, second_result), start=1)
    ]
    assert all(measurement is not None for measurement in measurements)
    barrier = threading.Barrier(2)
    exact_identities = {
        exact_evidence_key(tenant, resource.id, int(resource.version)): (
            resource.id,
            int(resource.version),
        )
        for resource in (first, second)
    }

    def record(measurement):
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            connection.execute(
                sql.SQL("set search_path to {}, public").format(
                    sql.Identifier(schema)
                )
            )
            connection.execute("set local lock_timeout = '2s'")
            barrier.wait(timeout=2)
            return RetrievalMetricsRepository(connection).record(
                measurement,
                exact_identities=exact_identities,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(record, measurement) for measurement in measurements]
        results = [future.result(timeout=5) for future in futures]
    assert [result.evidence_count for result in results] == [2, 2]


def test_outcomes_separate_explicit_adoption_schedule_and_censoring(migrated_conn) -> None:
    from psycopg.types.json import Jsonb

    from data_foundation.creation_memory import save_generated_copy_resource
    from data_foundation.repositories.generated_copy import GeneratedCopyRepository
    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-outcome"
    actor = "ou-owner"
    repo = ResourceRepository(migrated_conn)
    evidence = _qualify(repo, tenant_id=tenant, actor=actor)
    metrics_repo = RetrievalMetricsRepository(migrated_conn)

    def create_copy(turn: str, call: str):
        run = _record(
            metrics_repo,
            tenant_id=tenant,
            actor=actor,
            evidence=evidence,
            turn=turn,
            call=call,
        )
        assert run is not None
        copy = save_generated_copy_resource(
            repo,
            tenant_id=tenant,
            actor_open_id=actor,
            title="生成标题",
            body="生成正文",
            tags=["#测试"],
            evidence=[
                {
                    "resource_id": evidence.id,
                    "resource_version": int(evidence.version),
                }
            ],
            origin_turn_id=turn,
        )
        return run, copy

    explicit_run, explicit_copy = create_copy("turn-explicit", "call-explicit")
    schedule_run, schedule_copy = create_copy("turn-schedule", "call-schedule")
    recent_run, _ = create_copy("turn-recent", "call-recent")
    lifecycle = GeneratedCopyRepository(repo)

    explicit_state = lifecycle.get_state(
        tenant_id=tenant,
        actor_open_id=actor,
        resource_id=explicit_copy["resource"]["resource_id"],
    )
    lifecycle.adopt_version(
        tenant_id=tenant,
        actor_open_id=actor,
        resource_id=explicit_copy["resource"]["resource_id"],
        resource_version=explicit_copy["resource"]["resource_version"],
        expected_state_version=explicit_state.state_version,
    )

    schedule_state = lifecycle.get_state(
        tenant_id=tenant,
        actor_open_id=actor,
        resource_id=schedule_copy["resource"]["resource_id"],
    )
    lifecycle.finalize_for_schedule(
        tenant_id=tenant,
        actor_open_id=actor,
        resource_id=schedule_copy["resource"]["resource_id"],
        target_resource_version=schedule_copy["resource"]["resource_version"],
        expected_latest_resource_version=schedule_state.latest_resource_version,
        expected_state_version=schedule_state.state_version,
    )

    old = datetime.now(UTC) - timedelta(days=20)
    for run_id in (explicit_run.retrieval_run_id, schedule_run.retrieval_run_id):
        migrated_conn.execute(
            "update knowledge_retrieval_runs set created_at = %s where id = %s",
            (old, run_id),
        )
    explicit_id = explicit_copy["resource"]["resource_id"]
    schedule_id = schedule_copy["resource"]["resource_id"]
    migrated_conn.execute(
        """
        update resource_events set created_at = %s
        where tenant_id = %s and resource_id in (%s::uuid, %s::uuid)
          and event_type in ('adopted', 'finalized_for_schedule')
        """,
        (old + timedelta(days=1), tenant, explicit_id, schedule_id),
    )
    # A duplicated explicit event is still one adopted generated resource.
    explicit_event = migrated_conn.execute(
        """
        select payload from resource_events
        where tenant_id = %s and resource_id = %s and event_type = 'adopted'
        limit 1
        """,
        (tenant, explicit_id),
    ).fetchone()
    migrated_conn.execute(
        """
        insert into resource_events (
          tenant_id, resource_id, event_type, actor_open_id, payload, created_at
        ) values (%s, %s, 'adopted', %s, %s, %s)
        """,
        (
            tenant,
            explicit_id,
            actor,
            Jsonb(explicit_event["payload"]),
            old + timedelta(days=2),
        ),
    )
    # Keep the third cohort recent: it must be censored from both mature denominators.
    migrated_conn.execute(
        "update knowledge_retrieval_runs set created_at = now() where id = %s",
        (recent_run.retrieval_run_id,),
    )
    # Events happened after the synthetic cohort start and remain within both windows.
    metrics = metrics_repo.aggregate(
        tenant_id=tenant,
        actor_open_id=actor,
        as_of=datetime.now(UTC),
        min_sample_size=1,
    )
    assert metrics.attributed_copy_count == 3
    assert metrics.mature_explicit_copy_count == 2
    assert metrics.explicit_adopted_copy_count == 1
    assert metrics.explicit_adoption_rate == 0.5
    assert metrics.mature_committed_copy_count == 2
    assert metrics.committed_use_copy_count == 2
    assert metrics.committed_use_rate == 1.0
    assert metrics.censored_explicit_copy_count == 1
    assert metrics.censored_committed_copy_count == 1


def test_outcome_requires_same_actor_and_exact_provenance_source_version(
    migrated_conn,
) -> None:
    from data_foundation.creation_memory import save_generated_copy_resource
    from data_foundation.repositories.generated_copy import GeneratedCopyRepository
    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-exact-outcome"
    actor = "ou-owner"
    repo = ResourceRepository(migrated_conn)
    evidence = _qualify(repo, tenant_id=tenant, actor=actor)
    metrics_repo = RetrievalMetricsRepository(migrated_conn)
    run = _record(
        metrics_repo,
        tenant_id=tenant,
        actor=actor,
        evidence=evidence,
        turn="turn-exact",
        call="call-exact",
    )
    assert run is not None
    copy = save_generated_copy_resource(
        repo,
        tenant_id=tenant,
        actor_open_id=actor,
        title="exact attribution",
        body="generated body",
        tags=["#test"],
        evidence=[
            {
                "resource_id": evidence.id,
                "resource_version": int(evidence.version),
            }
        ],
        origin_turn_id="turn-exact",
    )
    copy_id = copy["resource"]["resource_id"]
    copy_version = int(copy["resource"]["resource_version"])
    lifecycle = GeneratedCopyRepository(repo)
    state = lifecycle.get_state(
        tenant_id=tenant, actor_open_id=actor, resource_id=copy_id
    )
    lifecycle.adopt_version(
        tenant_id=tenant,
        actor_open_id=actor,
        resource_id=copy_id,
        resource_version=copy_version,
        expected_state_version=state.state_version,
    )

    old = datetime.now(UTC) - timedelta(days=20)
    migrated_conn.execute(
        "update knowledge_retrieval_runs set created_at = %s where id = %s",
        (old, run.retrieval_run_id),
    )
    event = migrated_conn.execute(
        """
        update resource_events
        set created_at = %s, actor_open_id = 'ou-other'
        where tenant_id = %s and resource_id = %s and event_type = 'adopted'
        returning id
        """,
        (old + timedelta(days=1), tenant, copy_id),
    ).fetchone()
    assert event is not None

    def aggregate():
        return metrics_repo.aggregate(
            tenant_id=tenant,
            actor_open_id=actor,
            as_of=datetime.now(UTC),
            min_sample_size=1,
        )

    wrong_actor = aggregate()
    assert wrong_actor.attributed_copy_count == 1
    assert wrong_actor.explicit_adopted_copy_count == 0
    assert wrong_actor.committed_use_copy_count == 0

    migrated_conn.execute(
        """
        update resource_events
        set actor_open_id = %s,
            payload = jsonb_set(payload, '{version}', to_jsonb(999), true)
        where id = %s
        """,
        (actor, event["id"]),
    )
    wrong_version = aggregate()
    assert wrong_version.explicit_adopted_copy_count == 0
    assert wrong_version.committed_use_copy_count == 0

    migrated_conn.execute(
        """
        update resource_events
        set payload = jsonb_set(payload, '{version}', to_jsonb(%s::int), true)
        where id = %s
        """,
        (copy_version, event["id"]),
    )
    exact = aggregate()
    assert exact.explicit_adopted_copy_count == 1
    # Explicit adoption is also the first committed-use fact, counted once.
    assert exact.committed_use_copy_count == 1
    assert exact.committed_use_rate == 1.0


def test_multiversion_copy_is_one_cohort_and_requires_adopted_version_provenance(
    migrated_conn,
) -> None:
    from data_foundation.creation_memory import save_generated_copy_resource
    from data_foundation.repositories.generated_copy import GeneratedCopyRepository
    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-multiversion-outcome"
    actor = "ou-owner"
    repo = ResourceRepository(migrated_conn)
    evidence = _qualify(repo, tenant_id=tenant, actor=actor)
    metrics_repo = RetrievalMetricsRepository(migrated_conn)
    run = _record(
        metrics_repo,
        tenant_id=tenant,
        actor=actor,
        evidence=evidence,
        turn="turn-multiversion",
        call="call-multiversion",
    )
    assert run is not None
    versions = [
        {"label": label, "title": f"title-{label}", "body": f"body-{label}", "tags": ["#test"]}
        for label in ("A", "B", "C")
    ]
    copy = save_generated_copy_resource(
        repo,
        tenant_id=tenant,
        actor_open_id=actor,
        title=versions[0]["title"],
        body=versions[0]["body"],
        tags=versions[0]["tags"],
        versions=versions,
        evidence=[
            {
                "resource_id": evidence.id,
                "resource_version": int(evidence.version),
            }
        ],
        origin_turn_id="turn-multiversion",
    )
    copy_id = copy["resource"]["resource_id"]
    version_b = next(
        int(item["resource_version"])
        for item in copy["resource"]["versions"]
        if item["label"] == "B"
    )
    lifecycle = GeneratedCopyRepository(repo)
    state = lifecycle.get_state(
        tenant_id=tenant,
        actor_open_id=actor,
        resource_id=copy_id,
    )
    lifecycle.adopt_version(
        tenant_id=tenant,
        actor_open_id=actor,
        resource_id=copy_id,
        resource_version=version_b,
        expected_state_version=state.state_version,
    )

    old = datetime.now(UTC) - timedelta(days=20)
    migrated_conn.execute(
        "update knowledge_retrieval_runs set created_at = %s where id = %s",
        (old, run.retrieval_run_id),
    )
    migrated_conn.execute(
        """
        update resource_events set created_at = %s
        where tenant_id = %s and resource_id = %s and event_type = 'adopted'
        """,
        (old + timedelta(days=1), tenant, copy_id),
    )

    def aggregate():
        return metrics_repo.aggregate(
            tenant_id=tenant,
            actor_open_id=actor,
            as_of=datetime.now(UTC),
            min_sample_size=1,
        )

    exact = aggregate()
    assert exact.attributed_copy_count == 1
    assert exact.mature_explicit_copy_count == 1
    assert exact.explicit_adopted_copy_count == 1
    assert exact.committed_use_copy_count == 1

    migrated_conn.execute(
        """
        delete from resource_edges
        where tenant_id = %s and source_resource_id = %s
          and source_resource_version = %s
          and edge_type in ('derived_from', 'imitated_from')
        """,
        (tenant, copy_id, version_b),
    )
    wrong_version = aggregate()
    assert wrong_version.attributed_copy_count == 1
    assert wrong_version.mature_explicit_copy_count == 1
    assert wrong_version.explicit_adopted_copy_count == 0
    assert wrong_version.committed_use_copy_count == 0


def test_default_small_sample_suppresses_rates_and_per_evidence_rows(migrated_conn) -> None:
    from data_foundation.repositories.resource import ResourceRepository

    tenant = "tenant-small"
    actor = "ou-owner"
    repo = ResourceRepository(migrated_conn)
    evidence = _qualify(repo, tenant_id=tenant, actor=actor)
    metrics_repo = RetrievalMetricsRepository(migrated_conn)
    assert _record(
        metrics_repo,
        tenant_id=tenant,
        actor=actor,
        evidence=evidence,
        turn="turn-small",
        call="call-small",
    ) is not None
    metrics = metrics_repo.aggregate(
        tenant_id=tenant,
        actor_open_id=actor,
        as_of=datetime.now(UTC) + timedelta(days=30),
    )
    assert metrics.explicit_adoption_rate is None
    assert metrics.committed_use_rate is None
    assert metrics.sample_suppressed is True
    assert "evidence" not in safe_metrics_payload(metrics)
