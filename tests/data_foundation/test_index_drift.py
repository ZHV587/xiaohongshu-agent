import inspect
from types import SimpleNamespace

from data_foundation.index_drift import (
    TOPIC_GRAPH,
    TOPIC_MEILI,
    DriftEntry,
    detect_index_drift,
)
from scripts.detect_engine_drift import _expected_by_topic, _meili_counts


def test_no_drift_when_engines_match_expected():
    drift = detect_index_drift(
        expected_by_topic={TOPIC_MEILI: {"default": 100}, TOPIC_GRAPH: {"default": 100}},
        engine_actual={TOPIC_MEILI: {"default": 100}, TOPIC_GRAPH: {"default": 100}},
        engine_pending={},
    )
    assert drift == []


def test_pending_backlog_is_not_drift():
    # 引擎少 20,但有 20 在途 → 正常 backlog,不报丢失。
    drift = detect_index_drift(
        expected_by_topic={TOPIC_MEILI: {"default": 100}, TOPIC_GRAPH: {"default": 100}},
        engine_actual={TOPIC_MEILI: {"default": 80}, TOPIC_GRAPH: {"default": 80}},
        engine_pending={TOPIC_MEILI: {"default": 20}, TOPIC_GRAPH: {"default": 20}},
    )
    assert drift == []


def test_real_loss_detected_even_with_some_pending():
    # 引擎少 60,在途只有 10 → 即便消费完仍缺 50 → 真实丢失(graph 给满,只 meili 丢)。
    drift = detect_index_drift(
        expected_by_topic={TOPIC_MEILI: {"default": 100}, TOPIC_GRAPH: {"default": 100}},
        engine_actual={TOPIC_MEILI: {"default": 40}, TOPIC_GRAPH: {"default": 100}},
        engine_pending={TOPIC_MEILI: {"default": 10}},
    )
    assert drift == [
        DriftEntry(
            tenant_id="default",
            topic=TOPIC_MEILI,
            expected=100,
            actual=40,
            pending=10,
            missing=50,
        )
    ]


def test_missing_engine_count_treated_as_zero():
    # 引擎实际为空(卷丢失):无该 topic 的 actual 记录 → 视作 0 → 全量缺失。
    drift = detect_index_drift(
        expected_by_topic={TOPIC_MEILI: {"t1": 5}, TOPIC_GRAPH: {"t1": 5}},
        engine_actual={TOPIC_MEILI: {}, TOPIC_GRAPH: {}},
        engine_pending={},
    )
    topics = sorted(d.topic for d in drift)
    assert topics == sorted([TOPIC_MEILI, TOPIC_GRAPH])
    assert all(d.missing == 5 and d.actual == 0 for d in drift)


def test_zero_or_empty_tenant_skipped():
    drift = detect_index_drift(
        expected_by_topic={TOPIC_MEILI: {"empty": 0}, TOPIC_GRAPH: {"empty": 0}},
        engine_actual={TOPIC_MEILI: {}, TOPIC_GRAPH: {}},
        engine_pending={},
    )
    assert drift == []


def test_multi_tenant_only_flags_the_lost_one():
    drift = detect_index_drift(
        expected_by_topic={
            TOPIC_MEILI: {"ok": 10, "lost": 10},
            TOPIC_GRAPH: {"ok": 10, "lost": 10},
        },
        engine_actual={
            TOPIC_MEILI: {"ok": 10, "lost": 0},
            TOPIC_GRAPH: {"ok": 10, "lost": 10},
        },
        engine_pending={},
    )
    # 只有 lost 的 meili 缺(graph 完好),ok 全好
    assert drift == [
        DriftEntry("lost", TOPIC_MEILI, expected=10, actual=0, pending=0, missing=10)
    ]


def test_topic_specific_expected_excludes_unadopted_copy_from_meili_only():
    drift = detect_index_drift(
        expected_by_topic={
            TOPIC_MEILI: {"default": 7},
            TOPIC_GRAPH: {"default": 10},
        },
        engine_actual={
            TOPIC_MEILI: {"default": 7},
            TOPIC_GRAPH: {"default": 10},
        },
        engine_pending={},
    )
    assert drift == []


def test_disabled_engine_topic_is_skipped_not_reported_as_full_loss():
    drift = detect_index_drift(
        expected_by_topic={
            TOPIC_MEILI: {"default": 7},
            TOPIC_GRAPH: {"default": 10},
        },
        engine_actual={TOPIC_GRAPH: {"default": 10}},
        engine_pending={},
    )
    assert drift == []


def test_drift_expected_sql_keeps_graph_candidates_but_excludes_them_from_meili():
    source = inspect.getsource(_expected_by_topic)
    assert "count(*) as graph_n" in source
    assert "from current_knowledge_targets target" in source
    assert "as meili_n" in source


def test_meili_drift_uses_version_complete_count_not_raw_document_count(monkeypatch):
    from data_foundation.meili_client import MeiliResourceIndex, MeiliTenantAudit
    import scripts.detect_engine_drift as drift_script

    fake_index = SimpleNamespace(
        ensure_index=lambda: None,
        audit_tenant=lambda *, tenant_id: MeiliTenantAudit(
            total_documents=5,
            versioned_documents=4,
        ),
    )
    monkeypatch.setattr(
        drift_script,
        "meili_config_from_env",
        lambda: SimpleNamespace(state="enabled"),
    )
    monkeypatch.setattr(
        MeiliResourceIndex,
        "from_config",
        classmethod(lambda cls, config: fake_index),
    )

    usable, malformed = _meili_counts(["default"])
    drift = detect_index_drift(
        expected_by_topic={TOPIC_MEILI: {"default": 5}, TOPIC_GRAPH: {}},
        engine_actual={TOPIC_MEILI: usable},
        engine_pending={},
    )

    assert malformed == {"default": 1}
    assert drift == [
        DriftEntry("default", TOPIC_MEILI, expected=5, actual=4, pending=0, missing=1)
    ]
