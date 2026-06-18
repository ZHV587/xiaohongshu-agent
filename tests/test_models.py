import httpx
from middlewares import is_retryable_error


class FakeStatusError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


def test_is_retryable_error_on_503():
    assert is_retryable_error(FakeStatusError(503)) is True


def test_is_retryable_error_on_429():
    assert is_retryable_error(FakeStatusError(429)) is True


def test_is_retryable_error_on_400_is_false():
    assert is_retryable_error(FakeStatusError(400)) is False


def test_is_retryable_error_on_httpx_transport():
    assert is_retryable_error(httpx.ConnectError("boom")) is True


def test_is_retryable_error_on_value_error_is_false():
    assert is_retryable_error(ValueError("nope")) is False
