from data_foundation.index_drift import (
    TOPIC_GRAPH,
    TOPIC_MEILI,
    DriftEntry,
    detect_index_drift,
)


def test_no_drift_when_engines_match_expected():
    drift = detect_index_drift(
        expected_by_tenant={"default": 100},
        engine_actual={TOPIC_MEILI: {"default": 100}, TOPIC_GRAPH: {"default": 100}},
        engine_pending={},
    )
    assert drift == []


def test_pending_backlog_is_not_drift():
    # 引擎少 20,但有 20 在途 → 正常 backlog,不报丢失。
    drift = detect_index_drift(
        expected_by_tenant={"default": 100},
        engine_actual={TOPIC_MEILI: {"default": 80}, TOPIC_GRAPH: {"default": 80}},
        engine_pending={TOPIC_MEILI: {"default": 20}, TOPIC_GRAPH: {"default": 20}},
    )
    assert drift == []


def test_real_loss_detected_even_with_some_pending():
    # 引擎少 60,在途只有 10 → 即便消费完仍缺 50 → 真实丢失(graph 给满,只 meili 丢)。
    drift = detect_index_drift(
        expected_by_tenant={"default": 100},
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
        expected_by_tenant={"t1": 5},
        engine_actual={},
        engine_pending={},
    )
    topics = sorted(d.topic for d in drift)
    assert topics == sorted([TOPIC_MEILI, TOPIC_GRAPH])
    assert all(d.missing == 5 and d.actual == 0 for d in drift)


def test_zero_or_empty_tenant_skipped():
    drift = detect_index_drift(
        expected_by_tenant={"empty": 0},
        engine_actual={},
        engine_pending={},
    )
    assert drift == []


def test_multi_tenant_only_flags_the_lost_one():
    drift = detect_index_drift(
        expected_by_tenant={"ok": 10, "lost": 10},
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
