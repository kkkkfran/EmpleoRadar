from types import SimpleNamespace
from unittest.mock import Mock

from oci.exceptions import ServiceError

from oracle_retry.oci_client import with_retries


def test_rate_limit_retries(monkeypatch):
    monkeypatch.setattr("oracle_retry.oci_client.time.sleep", lambda _: None)
    call = Mock(side_effect=[ServiceError(429, "r", {}, "TooManyRequests"), "ok"])
    assert with_retries(call) == "ok"
    assert call.call_count == 2


def test_auth_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr("oracle_retry.oci_client.time.sleep", lambda _: None)
    call = Mock(side_effect=ServiceError(401, "r", {}, "NotAuthenticated"))
    try:
        with_retries(call)
    except ServiceError:
        pass
    assert call.call_count == 1
