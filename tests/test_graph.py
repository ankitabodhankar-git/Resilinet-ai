from resilinet import graph
from resilinet.config import Settings


class FakeGraph:
    def __init__(self, error=None):
        self.error = error
        self.queries = []

    def ro_query(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return object()


def test_get_graph_uses_official_client_configuration(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, **kwargs):
            calls.update(kwargs)

        def select_graph(self, graph_name):
            calls["graph_name"] = graph_name
            return "selected-graph"

    monkeypatch.setattr(graph, "FalkorDB", FakeClient)
    settings = Settings(
        _env_file=None,
        falkordb_host="db.local",
        falkordb_port=6380,
        falkordb_username="demo-user",
        falkordb_password="unit-test-placeholder",
        falkordb_graph="unit_test",
    )

    selected = graph.get_graph(settings)

    assert selected == "selected-graph"
    assert calls == {
        "host": "db.local",
        "port": 6380,
        "username": "demo-user",
        "password": "unit-test-placeholder",
        "graph_name": "unit_test",
    }


def test_connection_check_runs_read_only_query(monkeypatch):
    fake_graph = FakeGraph()
    monkeypatch.setattr(graph, "get_graph", lambda _settings=None: fake_graph)

    assert graph.check_graph_connection(Settings(_env_file=None)) is True
    assert fake_graph.queries == ["RETURN 1 AS ok"]


def test_connection_check_returns_false_when_client_connection_fails(monkeypatch):
    def fail_to_connect(_settings=None):
        raise ConnectionError("unavailable")

    monkeypatch.setattr(graph, "get_graph", fail_to_connect)

    assert graph.check_graph_connection(Settings(_env_file=None)) is False


def test_connection_check_returns_false_when_query_fails(monkeypatch):
    fake_graph = FakeGraph(error=TimeoutError("unavailable"))
    monkeypatch.setattr(graph, "get_graph", lambda _settings=None: fake_graph)

    assert graph.check_graph_connection(Settings(_env_file=None)) is False
