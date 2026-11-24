import pytest

from oracle_retry.config import ConfigurationError, Settings


def test_config_requires_fields(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    with pytest.raises(ConfigurationError, match="OCI_USER_OCID"):
        Settings.from_env()


def test_live_requires_persistent_bucket(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    with pytest.raises(ConfigurationError, match="OCI_STATE_BUCKET"):
        Settings.from_env()
