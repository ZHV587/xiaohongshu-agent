"""飞书效果列抽取纯函数测试(feishu-performance-metrics)。"""
from hypothesis import given, strategies as st

from data_foundation.feishu_metrics import (
    COLUMN_TO_METRIC,
    NOTE_LEVEL_TABLE_IDS,
    extract_performance_metrics,
)

_WHITELIST_TABLE = "tbl24vSVeLvz45ig"  # 🧲单篇采集库
_COMMENT_TABLE = "tblZgH0SF0AfYIpV"  # 💬评论采集库(排除)


def test_extract_maps_known_columns():
    fields = {"点赞数": 199000, "收藏数": 205000, "评论数": 4711, "转发数": 25000, "无关列": "x"}
    metrics = extract_performance_metrics(_WHITELIST_TABLE, "🧲单篇采集库", fields)
    assert metrics == {"likes": 199000, "collects": 205000, "comments": 4711, "shares": 25000}


def test_comment_table_excluded():
    """评论库即便带点赞数也不抽(评论点赞非笔记效果)。"""
    assert extract_performance_metrics(_COMMENT_TABLE, "💬评论采集库", {"点赞数": 100}) is None


def test_non_whitelist_table_returns_none():
    assert extract_performance_metrics("tblUnknown", "📜搜索下拉词", {"点赞数": 100}) is None


def test_missing_and_empty_and_invalid_columns_skipped():
    fields = {"点赞数": 50, "收藏数": "", "评论数": "abc", "转发数": -3}
    metrics = extract_performance_metrics(_WHITELIST_TABLE, "x", fields)
    assert metrics == {"likes": 50}  # 空/非数值/负值均跳过


def test_all_columns_absent_returns_none():
    assert extract_performance_metrics(_WHITELIST_TABLE, "x", {"标题": "t", "正文": "b"}) is None
    assert extract_performance_metrics(_WHITELIST_TABLE, "x", {}) is None
    assert extract_performance_metrics(_WHITELIST_TABLE, "x", None) is None


def test_numeric_string_parsed():
    metrics = extract_performance_metrics(_WHITELIST_TABLE, "x", {"点赞数": "1,069", "收藏数": "1309"})
    assert metrics == {"likes": 1069, "collects": 1309}


def test_bool_not_treated_as_number():
    assert extract_performance_metrics(_WHITELIST_TABLE, "x", {"点赞数": True}) is None


def test_deterministic():
    fields = {"点赞数": 10, "收藏数": 20}
    a = extract_performance_metrics(_WHITELIST_TABLE, "x", fields)
    b = extract_performance_metrics(_WHITELIST_TABLE, "x", dict(fields))
    assert a == b


@given(
    st.dictionaries(
        st.sampled_from(list(COLUMN_TO_METRIC) + ["噪声列", "标题"]),
        st.one_of(
            st.integers(min_value=-10, max_value=10**7),
            st.floats(allow_nan=True, allow_infinity=True),
            st.text(max_size=8),
            st.booleans(),
            st.none(),
        ),
        max_size=8,
    )
)
def test_property_never_raises_and_values_valid(fields):
    metrics = extract_performance_metrics(_WHITELIST_TABLE, "x", fields)
    if metrics is not None:
        assert metrics  # 非空
        assert set(metrics).issubset(set(COLUMN_TO_METRIC.values()))
        for v in metrics.values():
            assert isinstance(v, (int, float)) and v >= 0


@given(st.sampled_from([t for t in ["tblUnknown", "tblZgH0SF0AfYIpV", "x"] if t not in NOTE_LEVEL_TABLE_IDS]))
def test_property_non_whitelist_always_none(table_id):
    assert extract_performance_metrics(table_id, "n", {"点赞数": 999}) is None
