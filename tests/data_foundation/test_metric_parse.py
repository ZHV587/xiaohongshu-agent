from data_foundation.metric_parse import parse_count, parse_count_int


def test_parse_plain_numbers():
    assert parse_count(1234) == 1234.0
    assert parse_count(12.5) == 12.5
    assert parse_count("1234") == 1234.0
    assert parse_count("1,234") == 1234.0
    assert parse_count("  3.5  ") == 3.5


def test_parse_chinese_and_english_units():
    # 核心回归:爆款数值不再被丢成 0/None
    assert parse_count("1.2万") == 12000.0
    assert parse_count("10w+") == 100000.0
    assert parse_count("10W") == 100000.0
    assert parse_count("3亿") == 3e8
    assert parse_count("1.5万") == 15000.0
    assert parse_count("2千") == 2000.0
    assert parse_count("5k") == 5000.0
    assert parse_count("999+") == 999.0
    assert parse_count("1,234万") == 1234 * 1e4


def test_parse_invalid_and_negative_returns_none():
    assert parse_count(None) is None
    assert parse_count("") is None
    assert parse_count("abc") is None
    assert parse_count("万") is None        # 纯单位无数字
    assert parse_count("1.2.3") is None
    assert parse_count(-5) is None          # 负值
    assert parse_count(True) is None        # bool 不当数字
    assert parse_count(float("inf")) is None
    assert parse_count(float("nan")) is None


def test_parse_count_int_floors_and_zeroes():
    assert parse_count_int("1.2万") == 12000
    assert parse_count_int("3.7") == 3        # 截断
    assert parse_count_int("abc") == 0
    assert parse_count_int(None) == 0
    assert parse_count_int(-5) == 0
