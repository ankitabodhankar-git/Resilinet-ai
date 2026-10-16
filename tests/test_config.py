import pytest
from pydantic import ValidationError

from resilinet.config import Settings


def test_settings_load_falkordb_values_from_environment(monkeypatch):
    monkeypatch.setenv("FALKORDB_HOST", "graph.example.test")
    monkeypatch.setenv("FALKORDB_PORT", "6381")
    monkeypatch.setenv("FALKORDB_GRAPH", "test_graph")

    settings = Settings(_env_file=None)

    assert settings.falkordb_host == "graph.example.test"
    assert settings.falkordb_port == 6381
    assert settings.falkordb_graph == "test_graph"


def test_empty_optional_credentials_are_treated_as_unset(monkeypatch):
    monkeypatch.setenv("FALKORDB_USERNAME", "")
    monkeypatch.setenv("FALKORDB_PASSWORD", "")

    settings = Settings(_env_file=None)

    assert settings.falkordb_username is None
    assert settings.falkordb_password is None


@pytest.mark.parametrize("port", [0, 65536, "not-a-port"])
def test_settings_reject_invalid_ports(port):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, falkordb_port=port)
