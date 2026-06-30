from __future__ import annotations

"""Property 13（后端口径）：回填指标校验 `_clean_metrics` 的 Hypothesis 属性测试。

Feature: studio-data-integration, Property 13
Validates: Requirements 15.3

口径对齐前端 web/src/components/studio/backend-mappers.ts 的 validateBackfillMetrics：
- 入参非映射 → 拒绝
- 仅受支持指标（ALLOWED_METRICS）参与校验，其它键被忽略
- 受支持指标值无法转为数值 / 非有限 / 为负 → 拒绝
- 不含任何受支持指标 → 拒绝
当且仅当「全部受支持指标均为有限非负数值」且「至少含一个受支持指标」时通过。
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from data_foundation.performance_feedback import ALLOWED_METRICS, _clean_metrics


def _expected_valid_value(value: object) -> bool:
    """复刻 `_clean_metrics` 对单个受支持指标值的判定（oracle）。"""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if not math.isfinite(number):
        return False
    return number >= 0


def _expected_pass(metrics: dict[str, object]) -> bool:
    supported = [value for key, value in metrics.items() if key in ALLOWED_METRICS]
    if not supported:
        return False
    return all(_expected_valid_value(value) for value in supported)


# --- 生成器：覆盖 有限合法 / 负值 / 非有限 / 非数值 四类指标值 -----------------

_supported_keys = st.sampled_from(sorted(ALLOWED_METRICS))
_unsupported_keys = st.sampled_from(["unknown", "title", "noise", "点赞", "score"])

_valid_values = st.one_of(
    st.integers(min_value=0, max_value=10**7),
    st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
)
_negative_values = st.one_of(
    st.integers(min_value=-(10**7), max_value=-1),
    st.floats(min_value=-1e9, max_value=-0.001, allow_nan=False, allow_infinity=False),
)
_nonfinite_values = st.sampled_from([float("nan"), float("inf"), float("-inf")])
_nonnumeric_values = st.sampled_from(["abc", "1万", "", "  ", "1.2.3", None, "NaN前缀x"])

_any_value = st.one_of(
    _valid_values,
    _negative_values,
    _nonfinite_values,
    _nonnumeric_values,
)

# 混合受支持/不受支持键，值横跨四类；允许空映射与「仅不受支持键」两种边界。
_metrics_strategy = st.dictionaries(
    keys=st.one_of(_supported_keys, _unsupported_keys),
    values=_any_value,
    max_size=8,
)


# Feature: studio-data-integration, Property 13
@settings(max_examples=200)
@given(_metrics_strategy)
def test_clean_metrics_passes_iff_all_supported_finite_nonnegative(metrics):
    """当且仅当全部受支持指标为有限非负数值（且至少含一个）时校验通过。"""
    if _expected_pass(metrics):
        cleaned = _clean_metrics(metrics)
        # 通过时：结果非空、仅含受支持键、且键集合恰为输入中的受支持键
        assert cleaned
        assert set(cleaned).issubset(ALLOWED_METRICS)
        assert set(cleaned) == {key for key in metrics if key in ALLOWED_METRICS}
        for value in cleaned.values():
            assert isinstance(value, (int, float))
            assert math.isfinite(value) and value >= 0
    else:
        with pytest.raises(ValueError):
            _clean_metrics(metrics)


# Feature: studio-data-integration, Property 13
@settings(max_examples=200)
@given(
    valid=st.dictionaries(_supported_keys, _valid_values, min_size=1, max_size=6),
    bad_key=_supported_keys,
    bad_value=st.one_of(_negative_values, _nonfinite_values, _nonnumeric_values),
)
def test_any_invalid_supported_metric_forces_rejection(valid, bad_key, bad_value):
    """注入任一非数值/负值/非有限的受支持指标，必然拒绝（→ 方向）。"""
    metrics = {**valid, bad_key: bad_value}
    with pytest.raises(ValueError):
        _clean_metrics(metrics)


# Feature: studio-data-integration, Property 13
@settings(max_examples=200)
@given(st.dictionaries(_unsupported_keys, _any_value, max_size=6))
def test_no_supported_metric_always_rejected(metrics):
    """不含任何受支持指标（含空映射）一律拒绝。"""
    with pytest.raises(ValueError, match="at least one supported metric"):
        _clean_metrics(metrics)
